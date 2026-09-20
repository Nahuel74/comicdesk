"""Background workers for the GetComics download tab."""

from __future__ import annotations

import logging
import time
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from comicdesk.models import CBLBook, Comic
from comicdesk.services.comic_archive import read_comic_metadata
from comicdesk.services.getcomics import (
    CloudflareChallengeError,
    GetComicsClient,
    GetComicsDownloadLink,
    GetComicsDownloadError,
    GetComicsError,
    GetComicsIssue,
    GetComicsSearchResult,
    build_search_query,
    classify_link,
    pick_best_search_result,
)
from comicdesk.utils.filename_parser import parse_comic_filename

logger = logging.getLogger(__name__)


def _error_message(error: Exception) -> str:
    if isinstance(error, CloudflareChallengeError):
        return "Cloudflare blocked the request; try again or use manual download"
    if isinstance(error, GetComicsError):
        return str(error)
    return f"GetComics error: {error}"


def _build_comic_from_download(path: Path, issue: GetComicsIssue | None) -> Comic:
    suffix = path.suffix.lower()
    if suffix in (".cbz", ".cbr"):
        comic = read_comic_metadata(path)
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
        selected_link: GetComicsDownloadLink | None = None,
    ):
        super().__init__()
        self.issue = issue
        self.dest_dir = Path(dest_dir)
        self.selected_link = selected_link
        self._cancelled = False
        self._last_progress_emit = 0.0
        self._last_progress_percent = -1
        self._download_started = 0.0

    def _format_size(self, size: int) -> str:
        if size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        return f"{size / (1024 * 1024):.1f} MB"

    def _download_with_link_fallback(self, client: GetComicsClient) -> Path | None:
        tried_urls: set[str] = set()
        last_error: GetComicsDownloadError | None = None
        link = self.selected_link
        if link is not None and not isinstance(link, GetComicsDownloadLink):
            link = None

        while not self._cancelled:
            if link is None:
                self.progress.emit(2, 100, "Selecting download link...")
                link = client.pick_auto_download_link(
                    self.issue.download_links,
                    exclude_urls=tried_urls,
                )
                if link is None:
                    if tried_urls and last_error is not None:
                        raise last_error
                    logger.info(
                        "getcomics_worker_download_manual_links_required issue=%s",
                        self.issue.url,
                    )
                    if not self._cancelled:
                        self.manual_links_required.emit(self.issue.download_links)
                    return None

            if self._cancelled:
                raise GetComicsDownloadError("Download cancelled")

            failed_provider = link.provider
            failed_url = link.url
            try:
                if link.resolved_url and link.url not in tried_urls:
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
                    return None

                self._download_started = time.monotonic()
                self.progress.emit(10, 100, f"Downloading via {link.provider}...")
                return client.download_file(
                    link.url,
                    self.dest_dir,
                    resolved_url=resolved,
                    progress_callback=self._emit_download_progress,
                    cancelled=lambda: self._cancelled,
                    referer=self.issue.url,
                )
            except GetComicsDownloadError as exc:
                if self._cancelled or "cancelled" in str(exc).lower():
                    raise
                tried_urls.add(failed_url)
                last_error = exc
                link = None
                logger.warning(
                    "getcomics_worker_download_link_failed provider=%s url=%s error=%s",
                    failed_provider,
                    failed_url,
                    exc,
                )
                if not self._cancelled:
                    self.progress.emit(8, 100, "Trying another download link...")

        raise GetComicsDownloadError("Download cancelled")

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
            "getcomics_worker_download_started issue=%s dest_dir=%s selected_provider=%s",
            self.issue.url,
            self.dest_dir,
            getattr(self.selected_link, "provider", None),
        )
        try:
            with GetComicsClient() as client:
                path = self._download_with_link_fallback(client)
            if path is None:
                return

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


class WishlistDownloadWorker(QThread):
    """Resolve a CBL wishlist item to a GetComics issue."""

    finished = Signal(object, object)
    error = Signal(object, str)

    def __init__(self, book: CBLBook):
        super().__init__()
        self.book = book
        self._cancelled = False

    def run(self):
        if self._cancelled:
            return
        started = time.monotonic()
        query = build_search_query(self.book)
        logger.info("wishlist_worker_resolve_started query=%s", query)
        try:
            with GetComicsClient() as client:
                results = client.search_by_name(query, page=1)
                if self._cancelled:
                    return
                match = pick_best_search_result(self.book, results)
                if match is None:
                    if not results:
                        self.error.emit(self.book, f"No GetComics results for '{query}'")
                    else:
                        self.error.emit(
                            self.book,
                            f"No confident GetComics match for '{query}' — try manual search",
                        )
                    return
                issue = client.get_issue(match.url)
            if not self._cancelled:
                logger.info(
                    "wishlist_worker_resolve_finished query=%s issue=%s duration_ms=%d",
                    query,
                    issue.url,
                    int((time.monotonic() - started) * 1000),
                )
                self.finished.emit(self.book, issue)
        except Exception as exc:
            logger.exception(
                "wishlist_worker_resolve_failed query=%s duration_ms=%d",
                query,
                int((time.monotonic() - started) * 1000),
            )
            if not self._cancelled:
                self.error.emit(self.book, _error_message(exc))

    def cancel(self):
        self._cancelled = True


class WishlistBatchDownloadWorker(QThread):
    """Resolve multiple wishlist items sequentially."""

    progress = Signal(int, int, object)
    item_finished = Signal(object, object)
    item_error = Signal(object, str)
    finished = Signal(int, int)

    def __init__(self, books: list[CBLBook]):
        super().__init__()
        self.books = list(books)
        self._cancelled = False

    def run(self):
        resolved = 0
        failed = 0
        total = len(self.books)
        for index, book in enumerate(self.books, start=1):
            if self._cancelled:
                break
            self.progress.emit(index, total, book)
            query = build_search_query(book)
            try:
                with GetComicsClient() as client:
                    results = client.search_by_name(query, page=1)
                    if self._cancelled:
                        return
                    match = pick_best_search_result(book, results)
                    if match is None:
                        failed += 1
                        if not results:
                            message = f"No GetComics results for '{query}'"
                        else:
                            message = f"No confident GetComics match for '{query}'"
                        self.item_error.emit(book, message)
                        continue
                    issue = client.get_issue(match.url)
                if self._cancelled:
                    return
                resolved += 1
                self.item_finished.emit(book, issue)
            except Exception as exc:
                failed += 1
                if not self._cancelled:
                    self.item_error.emit(book, _error_message(exc))
        if not self._cancelled:
            self.finished.emit(resolved, failed)

    def cancel(self):
        self._cancelled = True
