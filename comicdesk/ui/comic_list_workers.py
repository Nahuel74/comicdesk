"""Background workers for library scan and bulk file rename."""

import logging
import os
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from comicdesk.models import Comic
from comicdesk.services.cbz_writer import CbzWriteError
from comicdesk.services.comic_archive import scan_comics, write_comic_metadata
from comicdesk.services.comicvine_api import ComicVineClient
from comicdesk.services.identification import (
    STATUS_CANDIDATES,
    STATUS_EMPTY,
    STATUS_EXACT,
    hydrate_issue_for_apply,
    identify_comic,
)
from comicdesk.services.metadata_session import MetadataSession
from comicdesk.ui.cbz_metadata_workers import _api_error_message
from comicdesk.utils.rename_template import (
    RenameFolderPlanRow,
    RenamePlanRow,
    RenameRowStatus,
)

logger = logging.getLogger(__name__)


@dataclass
class MetadataRefreshItemResult:
    """Outcome of refreshing one comic from Comic Vine."""

    comic: Comic
    outcome: str
    message: str = ""
    previous_path: str = ""


def refresh_comic_metadata_from_comicvine(comic: Comic, client) -> MetadataRefreshItemResult:
    """Identify, apply, and persist Comic Vine metadata for one library comic."""
    previous_path = str(comic.path)
    try:
        snapshot = deepcopy(comic)
        result = identify_comic(snapshot, client, issues_only=True)
        if result.status != STATUS_EXACT or result.issue is None:
            if result.status == STATUS_CANDIDATES:
                return MetadataRefreshItemResult(
                    comic,
                    "skipped",
                    "Comic Vine returned more than one possible issue. "
                    "Open the Metadata tab to choose the correct match.",
                )
            if result.status == STATUS_EMPTY:
                return MetadataRefreshItemResult(
                    comic,
                    "skipped",
                    "Comic Vine did not find a matching issue for this file.",
                )
            return MetadataRefreshItemResult(
                comic,
                "skipped",
                "This file could not be matched to a single Comic Vine issue.",
            )
        issue = hydrate_issue_for_apply(client, result.issue)
        session = MetadataSession(comic)
        session.apply_proposal(issue, overwrite=True)
        saved_path = write_comic_metadata(session.draft)
        session.draft.path = saved_path
        session.commit()
        path_changed = str(saved_path) != previous_path
        return MetadataRefreshItemResult(
            comic,
            "success",
            previous_path=previous_path if path_changed else "",
        )
    except CbzWriteError as exc:
        logger.exception("metadata_refresh_write_failed error_type=%s", type(exc).__name__)
        return MetadataRefreshItemResult(
            comic, "failed", f"Unable to save comic metadata: {exc}"
        )
    except Exception as exc:
        logger.exception("metadata_refresh_failed error_type=%s", type(exc).__name__)
        return MetadataRefreshItemResult(comic, "failed", _api_error_message(exc))


def metadata_refresh_status_line(results: list[MetadataRefreshItemResult]) -> str:
    """One-line summary for the library status label."""
    success = sum(1 for item in results if item.outcome == "success")
    skipped = sum(1 for item in results if item.outcome == "skipped")
    failed = sum(1 for item in results if item.outcome == "failed")
    parts = [f"Updated {success} archive(s)"]
    if skipped:
        parts.append(f"{skipped} skipped")
    if failed:
        parts.append(f"{failed} failed")
    return "; ".join(parts)


def format_metadata_refresh_details(
    results: list[MetadataRefreshItemResult],
    *,
    max_entries: int = 12,
) -> str:
    """Multi-line report for skipped and failed items."""
    skipped = [item for item in results if item.outcome == "skipped"]
    failed = [item for item in results if item.outcome == "failed"]
    if not skipped and not failed:
        return ""
    lines: list[str] = []
    success = sum(1 for item in results if item.outcome == "success")
    if success:
        lines.append(f"Updated {success} archive(s).")
        lines.append("")
    if skipped:
        lines.append("Not updated (identification):")
        shown = skipped[:max_entries]
        for item in shown:
            name = Path(item.comic.path).name
            detail = item.message or "Could not identify this issue."
            lines.append(f"• {name} — {detail}")
        remaining = len(skipped) - len(shown)
        if remaining > 0:
            lines.append(f"• …and {remaining} more")
        lines.append("")
    if failed:
        lines.append("Could not save:")
        shown = failed[:max_entries]
        for item in shown:
            name = Path(item.comic.path).name
            detail = item.message or "Unknown error."
            lines.append(f"• {name} — {detail}")
        remaining = len(failed) - len(shown)
        if remaining > 0:
            lines.append(f"• …and {remaining} more")
    return "\n".join(lines).rstrip()


class FolderMetadataRefreshWorker(QThread):
    """Sequentially refresh Comic Vine metadata for a folder or selection."""

    progress = Signal(int, int, str)
    item_saved = Signal(object, str)
    finished = Signal(list)

    def __init__(
        self,
        comics: list[Comic],
        api_key: str,
        cache_enabled: bool = True,
    ):
        super().__init__()
        self.comics = list(comics)
        self.api_key = str(api_key or "").strip()
        self.cache_enabled = bool(cache_enabled)
        self._cancelled = False

    def run(self):
        results: list[MetadataRefreshItemResult] = []
        if not self.api_key or not self.comics:
            self.finished.emit(results)
            return
        client = ComicVineClient(self.api_key, cache_enabled=self.cache_enabled)
        total = len(self.comics)
        for index, comic in enumerate(self.comics):
            if self._cancelled:
                break
            name = Path(comic.path).name
            self.progress.emit(index + 1, total, name)
            item = refresh_comic_metadata_from_comicvine(comic, client)
            results.append(item)
            if item.outcome == "success":
                self.item_saved.emit(comic, item.previous_path)
        self.finished.emit(results)

    def cancel(self):
        self._cancelled = True


@dataclass
class RenameResult:
    """Outcome of renaming one CBZ file on disk."""

    comic: Comic
    old_path: Path
    new_path: Path | None
    error: str = ""


@dataclass
class FolderRenameResult:
    """Outcome of renaming one series folder on disk."""

    row: RenameFolderPlanRow
    folder_new: Path | None
    library_root_old: Path | None = None
    library_root_new: Path | None = None
    error: str = ""


class FolderRenameWorker(QThread):
    """Rename series folders and update comic paths under each renamed tree."""

    progress = Signal(int, int, str)
    finished = Signal(list)

    def __init__(
        self,
        rows: list[RenameFolderPlanRow],
        library_root: Path,
    ):
        super().__init__()
        self.rows = [row for row in rows if row.status == RenameRowStatus.OK]
        self.library_root = Path(library_root).resolve()
        self._cancelled = False

    def run(self):
        results: list[FolderRenameResult] = []
        total = len(self.rows)
        staged: list[tuple[RenameFolderPlanRow, Path]] = []

        for index, row in enumerate(self.rows):
            if self._cancelled:
                for pending_row, pending_temp in staged:
                    self._restore_temp(pending_row, pending_temp, results)
                break
            old_folder = row.folder_old
            temp_path = old_folder.with_name(
                f".comicdesk-folder-rename-{index}-{old_folder.name}"
            )
            try:
                old_folder.rename(temp_path)
                staged.append((row, temp_path))
            except OSError as exc:
                results.append(
                    FolderRenameResult(row, None, error=str(exc))
                )
            self.progress.emit(index + 1, total, old_folder.name)

        root_old = self.library_root

        for index, (row, temp_path) in enumerate(staged):
            if self._cancelled:
                self._restore_temp(row, temp_path, results)
                continue
            proposed = row.folder_new
            if proposed is None:
                self._restore_temp(row, temp_path, results)
                continue
            try:
                temp_path.rename(proposed)
                old_folder = row.folder_old.resolve()
                prefix_old = str(old_folder)
                prefix_new = str(proposed.resolve())
                for comic in row.comics:
                    path_str = str(comic.path.resolve())
                    if path_str == prefix_old or path_str.startswith(prefix_old + os.sep):
                        suffix = path_str[len(prefix_old) :]
                        comic.path = Path(prefix_new + suffix)
                lib_old = root_old if old_folder == root_old else None
                lib_new = proposed.resolve() if old_folder == root_old else None
                results.append(
                    FolderRenameResult(
                        row,
                        proposed,
                        library_root_old=lib_old,
                        library_root_new=lib_new,
                    )
                )
            except OSError as exc:
                results.append(FolderRenameResult(row, None, error=str(exc)))
                self._restore_temp(row, temp_path, results)
            self.progress.emit(index + 1, total, proposed.name)

        self.finished.emit(results)

    def _restore_temp(
        self,
        row: RenameFolderPlanRow,
        temp_path: Path,
        results: list[FolderRenameResult],
    ):
        if not temp_path.exists():
            return
        try:
            temp_path.rename(row.folder_old)
        except OSError as exc:
            results.append(
                FolderRenameResult(row, None, error=f"Restore failed: {exc}")
            )

    def cancel(self):
        self._cancelled = True


class RenameWorker(QThread):
    """Rename CBZ files on disk using a two-phase temp rename for batch safety."""

    progress = Signal(int, int, str)
    finished = Signal(list)

    def __init__(self, rows: list[RenamePlanRow]):
        super().__init__()
        self.rows = [row for row in rows if row.status == RenameRowStatus.OK]
        self._cancelled = False

    def run(self):
        results: list[RenameResult] = []
        total = len(self.rows)
        staged: list[tuple[RenamePlanRow, Path]] = []

        for index, row in enumerate(self.rows):
            if self._cancelled:
                for pending_row, pending_temp in staged:
                    self._restore_temp(pending_row, pending_temp, results)
                break
            temp_path = row.old_path.with_name(f".comicdesk-rename-{index}-{row.old_path.name}")
            try:
                row.old_path.rename(temp_path)
                staged.append((row, temp_path))
            except OSError as exc:
                results.append(
                    RenameResult(row.comic, row.old_path, None, str(exc))
                )
            self.progress.emit(index + 1, total, row.old_path.name)

        for index, (row, temp_path) in enumerate(staged):
            if self._cancelled:
                self._restore_temp(row, temp_path, results)
                continue
            proposed = row.proposed_path
            if proposed is None:
                self._restore_temp(row, temp_path, results)
                continue
            try:
                temp_path.rename(proposed)
                results.append(RenameResult(row.comic, row.old_path, proposed, ""))
            except OSError as exc:
                results.append(RenameResult(row.comic, row.old_path, None, str(exc)))
                self._restore_temp(row, temp_path, results)
            self.progress.emit(index + 1, total, proposed.name)

        self.finished.emit(results)

    def _restore_temp(self, row: RenamePlanRow, temp_path: Path, results: list[RenameResult]):
        if not temp_path.exists():
            return
        try:
            temp_path.rename(row.old_path)
        except OSError as exc:
            results.append(
                RenameResult(row.comic, row.old_path, None, f"Restore failed: {exc}")
            )

    def cancel(self):
        self._cancelled = True


class ScanWorker(QThread):
    finished = Signal(list)
    progress = Signal(int, int, str)
    error = Signal(str)

    def __init__(self, path: Path, recursive=True):
        super().__init__()
        self.path, self.recursive, self._cancelled = path, recursive, False

    def run(self):
        comics = scan_comics(
            self.path,
            self.recursive,
            progress=lambda current, total, name: self.progress.emit(current, total, name),
            on_error=self.error.emit,
            cancelled=lambda: self._cancelled,
        )
        self.finished.emit(comics)

    def cancel(self):
        self._cancelled = True
