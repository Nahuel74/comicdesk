"""Qt workers for the Pages workflow."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from comicdesk.services.comic_pages import (
    list_image_pages,
    read_image_member_bytes,
    remove_image_pages,
    rename_image_members,
)
from comicdesk.services.cbz_writer import CbzWriteError
from comicdesk.models import Comic
from comicdesk.utils.page_rename_template import (
    RenamePageMemberRow,
    full_rename_map_for_comic,
)
from comicdesk.utils.rename_template import RenameRowStatus

logger = logging.getLogger(__name__)


def _log_name_sample(names: list[str], *, limit: int = 5) -> str:
    if not names:
        return ""
    if len(names) <= limit:
        return ", ".join(names)
    sample = ", ".join(names[:limit])
    return f"{sample}, … (+{len(names) - limit} more)"


class PagesListWorker(QThread):
    """Load image member names for one archive off the UI thread."""

    finished = Signal(object)
    error = Signal(str)

    def __init__(self, path: Path, token: int = 0):
        super().__init__()
        self.path = Path(path)
        self.token = token
        self._cancelled = False

    def run(self):
        if self._cancelled:
            return
        try:
            pages = list_image_pages(self.path)
            if not self._cancelled:
                self.finished.emit(pages)
        except CbzWriteError as exc:
            if not self._cancelled:
                self.error.emit(str(exc))
        except Exception as exc:
            if not self._cancelled:
                self.error.emit(f"Unable to list pages: {exc}")

    def cancel(self):
        self._cancelled = True


class PagesRemoveWorker(QThread):
    """Remove selected image members from an archive off the UI thread."""

    finished = Signal(object)
    error = Signal(str)

    def __init__(self, path: Path, names: list[str], token: int = 0):
        super().__init__()
        self.path = Path(path)
        self.names = list(names)
        self.token = token
        self._cancelled = False

    def run(self):
        if self._cancelled:
            return
        try:
            logger.info(
                "pages_remove_start archive=%s count=%d names=%s",
                self.path.name,
                len(self.names),
                _log_name_sample(self.names),
            )
            saved_path = remove_image_pages(self.path, self.names)
            if not self._cancelled:
                logger.info(
                    "pages_remove_done archive=%s saved=%s removed=%d",
                    self.path.name,
                    Path(saved_path).name,
                    len(self.names),
                )
                self.finished.emit(saved_path)
        except CbzWriteError as exc:
            if not self._cancelled:
                logger.warning(
                    "pages_remove_failed archive=%s error=%s",
                    self.path.name,
                    exc,
                )
                self.error.emit(str(exc))
        except Exception as exc:
            if not self._cancelled:
                logger.exception(
                    "pages_remove_failed archive=%s error_type=%s",
                    self.path.name,
                    type(exc).__name__,
                )
                self.error.emit(f"Unable to remove pages: {exc}")

    def cancel(self):
        self._cancelled = True


class PagesPreviewWorker(QThread):
    """Load one archive image member off the UI thread."""

    finished = Signal(object)
    error = Signal(str)

    def __init__(self, path: Path, member_name: str, token: int = 0):
        super().__init__()
        self.path = Path(path)
        self.member_name = member_name
        self.token = token
        self._cancelled = False

    def run(self):
        if self._cancelled:
            return
        try:
            data = read_image_member_bytes(self.path, self.member_name)
            if not self._cancelled:
                self.finished.emit(data)
        except CbzWriteError as exc:
            if not self._cancelled:
                self.error.emit(str(exc))
        except Exception as exc:
            if not self._cancelled:
                self.error.emit(f"Unable to load preview: {exc}")

    def cancel(self):
        self._cancelled = True


class PagesFolderCleanWorker(QThread):
    """Remove detected extras from multiple archives sequentially."""

    progress = Signal(int, int, str)
    finished = Signal(object)
    error = Signal(str)

    def __init__(self, jobs: list[tuple[Comic, list[str]]], token: int = 0):
        super().__init__()
        self.jobs = list(jobs)
        self.token = token
        self._cancelled = False

    def run(self):
        if self._cancelled:
            return
        results: list[tuple[Comic, Path, str]] = []
        total = len(self.jobs)
        try:
            for index, (comic, names) in enumerate(self.jobs, start=1):
                if self._cancelled:
                    return
                previous = str(comic.path)
                logger.info(
                    "pages_auto_clean_issue archive=%s index=%d/%d removing=%d names=%s",
                    Path(previous).name,
                    index,
                    total,
                    len(names),
                    _log_name_sample(names),
                )
                saved = remove_image_pages(Path(comic.path), names)
                results.append((comic, saved, previous))
                detail = (
                    f"{Path(previous).name}: deleted {len(names)} page(s) "
                    f"({_log_name_sample(names, limit=3)})"
                )
                self.progress.emit(index, total, detail)
            if not self._cancelled:
                logger.info(
                    "pages_auto_clean_done issues=%d total_pages=%d",
                    len(results),
                    sum(len(names) for _c, names in self.jobs[: len(results)]),
                )
                self.finished.emit(results)
        except CbzWriteError as exc:
            if not self._cancelled:
                self.error.emit(str(exc))
        except Exception as exc:
            if not self._cancelled:
                self.error.emit(f"Unable to clean folder: {exc}")

    def cancel(self):
        self._cancelled = True


class PagesRenameWorker(QThread):
    """Rename image members inside multiple archives sequentially."""

    progress = Signal(int, int, str)
    finished = Signal(object)
    error = Signal(str)

    def __init__(self, rows: list[RenamePageMemberRow], token: int = 0):
        super().__init__()
        self._all_rows = list(rows)
        self.rows = [row for row in rows if row.status == RenameRowStatus.OK]
        self.token = token
        self._cancelled = False

    def run(self):
        if self._cancelled:
            return
        by_comic: dict[int, list[RenamePageMemberRow]] = {}
        comics_order: list[Comic] = []
        for row in self.rows:
            key = id(row.comic)
            if key not in by_comic:
                by_comic[key] = []
                comics_order.append(row.comic)
            by_comic[key].append(row)

        results: list[tuple[Comic, Path, str]] = []
        total = len(comics_order)
        try:
            for index, comic in enumerate(comics_order, start=1):
                if self._cancelled:
                    return
                comic_rows = [
                    row for row in self._all_rows if row.comic is comic
                ]
                mapping = full_rename_map_for_comic(comic_rows, comic)
                if not mapping:
                    continue
                previous = str(comic.path)
                sample = _log_name_sample(
                    [f"{old} → {new}" for old, new in list(mapping.items())[:3]],
                    limit=3,
                )
                logger.info(
                    "pages_rename_issue archive=%s index=%d/%d pages=%d sample=%s",
                    Path(previous).name,
                    index,
                    total,
                    len(mapping),
                    sample,
                )
                saved = rename_image_members(Path(comic.path), mapping)
                results.append((comic, saved, previous))
                detail = (
                    f"{Path(previous).name}: renamed {len(mapping)} page(s)"
                )
                if sample:
                    detail = f"{detail} ({sample})"
                self.progress.emit(index, total, detail)
            if not self._cancelled:
                logger.info(
                    "pages_rename_done archives=%d total_pages=%d",
                    len(results),
                    len(self.rows),
                )
                self.finished.emit(results)
        except CbzWriteError as exc:
            if not self._cancelled:
                logger.warning("pages_rename_failed error=%s", exc)
                self.error.emit(str(exc))
        except Exception as exc:
            if not self._cancelled:
                logger.exception(
                    "pages_rename_failed error_type=%s",
                    type(exc).__name__,
                )
                self.error.emit(f"Unable to rename pages: {exc}")

    def cancel(self):
        self._cancelled = True
