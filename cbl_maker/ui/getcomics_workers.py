"""Background workers for the GetComics download tab."""

from __future__ import annotations

import logging
import time
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from cbl_maker.models import Comic
from cbl_maker.services.cbz_reader import read_cbz_metadata
from cbl_maker.services.cbz_writer import write_cbz_metadata
from cbl_maker.services.comicvine_api import ComicVineClient, ComicVineError
from cbl_maker.services.getcomics import (
    CloudflareChallengeError,
    GetComicsClient,
    GetComicsDownloadLink,
    GetComicsDownloadError,
    GetComicsError,
    GetComicsIssue,
    GetComicsSearchResult,
    classify_link,
)
from cbl_maker.services.identification import apply_issue_to_comic, identify_comic
from cbl_maker.utils.filename_parser import parse_comic_filename

logger = logging.getLogger(__name__)


def _error_message(error: Exception) -> str:
    if isinstance(error, CloudflareChallengeError):
        return "Cloudflare blocked the request; try again or use manual download"
    if isinstance(error, GetComicsError):
        return str(error)
    return f"GetComics error: {error}"


def _build_comic_from_download(path: Path, issue: GetComicsIssue | None) -> Comic:
    suffix = path.suffix.lower()
    if suffix == ".cbz":
        comic = read_cbz_metadata(path)
    else:
        comic = Comic(path=path)
        parsed = parse_comic_filename(path)
        comic.series_name = parsed.series_name
        comic.issue_number = parsed.issue_number
        comic.volume = parsed.volume
        comic.year = parsed.year

    if issue is not None:
        if issue.series_name and not comic.series_name:
            comic.series_name = issue.series_name
        if issue.issue_number and not comic.issue_number:
            comic.issue_number = issue.issue_number
        if issue.year and not comic.year:
            comic.year = issue.year
        if issue.title and not comic.title:
            comic.title = issue.title
        note = f"GetComics: {issue.url}"
        if note not in (comic.notes or ""):
            comic.notes = f"{comic.notes}\n{note}".strip() if comic.notes else note
        if issue.url and issue.url not in comic.web_links:
            comic.web_links.append(issue.url)
    return comic


def _enrich_comic(
    comic: Comic,
    api_key: str,
    cache_enabled: bool,
) -> tuple[Comic, str]:
    if not api_key:
        return comic, "Download complete (no API key for enrichment)"
    try:
        client = ComicVineClient(api_key, cache_enabled=cache_enabled)
        result = identify_comic(comic, client)
        if result.is_exact and result.issue is not None:
            apply_issue_to_comic(comic, result.issue, overwrite=True)
            if comic.path.suffix.lower() == ".cbz":
                write_cbz_metadata(comic)
            return comic, "Download complete and metadata enriched from Comic Vine"
        if result.candidates:
            return comic, "Download complete; multiple Comic Vine matches — refine in Metadata tab"
        return comic, "Download complete; no Comic Vine match found"
    except ComicVineError as exc:
        logger.warning("getcomics_enrich_failed error=%s", exc)
        return comic, f"Download complete; Comic Vine enrichment failed: {exc}"


class GetComicsSearchWorker(QThread):
    finished = Signal(list)
    error = Signal(str)

    def __init__(self, criterion: str, query: str, page: int = 1):
        super().__init__()
        self.criterion = criterion
        self.query = query
        self.page = page
        self._cancelled = False

    def run(self):
        if self._cancelled:
            return
        started = time.monotonic()
        logger.info(
            "getcomics_worker_search_started criterion=%s query=%s page=%d",
            self.criterion,
            self.query,
            self.page,
        )
        try:
            with GetComicsClient() as client:
                if self.criterion == "name":
                    results = client.search_by_name(self.query, self.page)
                elif self.criterion == "category":
                    results = client.search_by_category(self.query, self.page)
                elif self.criterion == "tag":
                    results = client.search_by_tag(self.query, self.page)
                else:
                    self.error.emit(f"Unknown search criterion: {self.criterion}")
                    return
            if not self._cancelled:
                logger.info(
                    "getcomics_worker_search_finished criterion=%s result_count=%d duration_ms=%d",
                    self.criterion,
                    len(results),
                    int((time.monotonic() - started) * 1000),
                )
                self.finished.emit(results)
        except Exception as exc:
            logger.exception("getcomics_search_failed duration_ms=%d", int((time.monotonic() - started) * 1000))
            if not self._cancelled:
                self.error.emit(_error_message(exc))

    def cancel(self):
        self._cancelled = True


class GetComicsThumbnailWorker(QThread):
    finished = Signal(bytes)
    error = Signal(str)

    def __init__(self, url: str, token: int = 0):
        super().__init__()
        self.url = url
        self.token = token
        self._cancelled = False

    def run(self):
        if self._cancelled or not self.url:
            return
        started = time.monotonic()
        logger.info("getcomics_worker_thumbnail_started url=%s token=%d", self.url, self.token)
        try:
            with GetComicsClient() as client:
                data = client.fetch_image_bytes(self.url)
            if not self._cancelled:
                logger.info(
                    "getcomics_worker_thumbnail_finished url=%s bytes=%d duration_ms=%d",
                    self.url,
                    len(data),
                    int((time.monotonic() - started) * 1000),
                )
                self.finished.emit(data)
        except Exception as exc:
            logger.exception(
                "getcomics_thumbnail_failed url=%s duration_ms=%d",
                self.url,
                int((time.monotonic() - started) * 1000),
            )
            if not self._cancelled:
                self.error.emit(_error_message(exc))

    def cancel(self):
        self._cancelled = True


class GetComicsIssueWorker(QThread):
    finished = Signal(object)
    error = Signal(str)

    def __init__(self, url: str):
        super().__init__()
        self.url = url
        self._cancelled = False

    def run(self):
        if self._cancelled:
            return
        started = time.monotonic()
        logger.info("getcomics_worker_issue_started url=%s", self.url)
        try:
            with GetComicsClient() as client:
                issue = client.get_issue(self.url)
            if not self._cancelled:
                logger.info(
                    "getcomics_worker_issue_finished url=%s link_count=%d duration_ms=%d",
                    self.url,
                    len(issue.download_links),
                    int((time.monotonic() - started) * 1000),
                )
                self.finished.emit(issue)
        except Exception as exc:
            logger.exception(
                "getcomics_issue_failed url=%s duration_ms=%d",
                self.url,
                int((time.monotonic() - started) * 1000),
            )
            if not self._cancelled:
                self.error.emit(_error_message(exc))

    def cancel(self):
        self._cancelled = True


class GetComicsDownloadWorker(QThread):
    progress = Signal(int, int, str)
    finished = Signal(object)
    error = Signal(str)
    cancelled = Signal()
    manual_links_required = Signal(list)

    def __init__(
        self,
        issue: GetComicsIssue,
        dest_dir: Path,
        *,
        api_key: str = "",
        cache_enabled: bool = True,
        auto_enrich: bool = True,
        selected_link: GetComicsDownloadLink | None = None,
    ):
        super().__init__()
        self.issue = issue
        self.dest_dir = Path(dest_dir)
        self.api_key = str(api_key or "").strip()
        self.cache_enabled = bool(cache_enabled)
        self.auto_enrich = bool(auto_enrich)
        self.selected_link = selected_link
        self._cancelled = False
        self._last_progress_emit = 0.0
        self._last_progress_percent = -1
        self._download_started = 0.0

    def _format_size(self, size: int) -> str:
        if size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        return f"{size / (1024 * 1024):.1f} MB"

    def _emit_download_progress(self, downloaded: int, total: int | None) -> None:
        now = time.monotonic()
        elapsed = now - self._download_started if self._download_started else 0.0
        speed = downloaded / elapsed if elapsed > 0 else 0.0
        if total and total > 0:
            percent = 10 + int(75 * downloaded / total)
            eta = int((total - downloaded) / speed) if speed > 0 else 0
            message = (
                f"Downloading... {self._format_size(downloaded)} / {self._format_size(total)}"
                f" @ {self._format_size(int(speed))}/s"
                f"{f' — ~{eta // 60}m {eta % 60}s left' if eta > 0 else ''}"
            )
        else:
            percent = min(84, 10 + downloaded // (5 * 1024 * 1024))
            message = (
                f"Downloading... {self._format_size(downloaded)}"
                f" @ {self._format_size(int(speed))}/s"
            )
        if (
            percent == self._last_progress_percent
            and now - self._last_progress_emit < 0.5
            and (not total or downloaded < total)
        ):
            return
        self._last_progress_emit = now
        self._last_progress_percent = percent
        self.progress.emit(percent, 100, message)

    def run(self):
        if self._cancelled:
            return
        started = time.monotonic()
        logger.info(
            "getcomics_worker_download_started issue=%s dest_dir=%s auto_enrich=%s selected_provider=%s",
            self.issue.url,
            self.dest_dir,
            self.auto_enrich,
            getattr(self.selected_link, "provider", None),
        )
        try:
            with GetComicsClient() as client:
                link = self.selected_link
                if link is None:
                    self.progress.emit(2, 100, "Selecting download link...")
                    link = client.pick_auto_download_link(self.issue.download_links)
                    if link is None:
                        logger.info(
                            "getcomics_worker_download_manual_links_required issue=%s",
                            self.issue.url,
                        )
                        if not self._cancelled:
                            self.manual_links_required.emit(self.issue.download_links)
                        return

                if self._cancelled:
                    return
                if link.resolved_url:
                    resolved = link.resolved_url
                    logger.info(
                        "getcomics_worker_download_using_cached_resolve provider=%s resolved=%s",
                        link.provider,
                        resolved,
                    )
                else:
                    self.progress.emit(5, 100, f"Resolving {link.provider}...")
                    resolved = client.resolve_redirect(link.url)
                    logger.info(
                        "getcomics_worker_download_resolved provider=%s source=%s resolved=%s",
                        link.provider,
                        link.url,
                        resolved,
                    )
                if not classify_link(link, resolved):
                    logger.info(
                        "getcomics_worker_download_manual_links_required provider=%s resolved=%s",
                        link.provider,
                        resolved,
                    )
                    if not self._cancelled:
                        self.manual_links_required.emit(self.issue.download_links)
                    return

                if self._cancelled:
                    return
                self._download_started = time.monotonic()
                self.progress.emit(10, 100, "Downloading file...")
                path = client.download_file(
                    link.url,
                    self.dest_dir,
                    resolved_url=resolved,
                    progress_callback=self._emit_download_progress,
                    cancelled=lambda: self._cancelled,
                    referer=self.issue.url,
                )

            if self._cancelled:
                logger.info(
                    "getcomics_worker_download_cancelled issue=%s duration_ms=%d",
                    self.issue.url,
                    int((time.monotonic() - started) * 1000),
                )
                self.cancelled.emit()
                return
            comic = _build_comic_from_download(path, self.issue)
            message = "Download complete"
            if self.auto_enrich and path.suffix.lower() == ".cbz":
                enrich_started = time.monotonic()
                self.progress.emit(90, 100, "Enriching metadata from Comic Vine...")
                logger.info("getcomics_worker_enrich_started path=%s", path)
                comic, message = _enrich_comic(comic, self.api_key, self.cache_enabled)
                logger.info(
                    "getcomics_worker_enrich_finished path=%s duration_ms=%d",
                    path,
                    int((time.monotonic() - enrich_started) * 1000),
                )
            elif path.suffix.lower() != ".cbz":
                message = "Download complete (metadata enrichment only supports CBZ)"

            if not self._cancelled:
                logger.info(
                    "getcomics_worker_download_finished path=%s duration_ms=%d",
                    path,
                    int((time.monotonic() - started) * 1000),
                )
                self.progress.emit(100, 100, message)
                self.finished.emit(comic)
        except GetComicsDownloadError as exc:
            if self._cancelled or "cancelled" in str(exc).lower():
                logger.info(
                    "getcomics_worker_download_cancelled issue=%s duration_ms=%d",
                    self.issue.url,
                    int((time.monotonic() - started) * 1000),
                )
                if not self._cancelled:
                    self._cancelled = True
                self.cancelled.emit()
                return
            logger.exception(
                "getcomics_download_failed issue=%s duration_ms=%d",
                self.issue.url,
                int((time.monotonic() - started) * 1000),
            )
            if not self._cancelled:
                self.error.emit(_error_message(exc))
        except Exception as exc:
            logger.exception(
                "getcomics_download_failed issue=%s duration_ms=%d",
                self.issue.url,
                int((time.monotonic() - started) * 1000),
            )
            if self._cancelled:
                self.cancelled.emit()
                return
            self.error.emit(_error_message(exc))

    def cancel(self):
        logger.info("getcomics_worker_download_cancel_requested issue=%s", self.issue.url)
        self._cancelled = True
