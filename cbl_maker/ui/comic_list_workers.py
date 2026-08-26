"""Background workers for scanning and Comic Vine enrichment."""

from pathlib import Path
import re
from PySide6.QtCore import QThread, Signal

from cbl_maker.models import Comic
from cbl_maker.services.cbz_reader import read_cbz_metadata
from cbl_maker.services.comicvine_api import (
    ComicVineClient, ComicVineError, RateLimitError, InvalidAPIKeyError,
)
from cbl_maker.utils.url_parser import extract_comicvine_ids


class ScanWorker(QThread):
    finished = Signal(list)
    progress = Signal(str)

    def __init__(self, path: Path, recursive=True):
        super().__init__()
        self.path, self.recursive, self._cancelled = path, recursive, False

    def run(self):
        comics = []
        pattern = "**/*.cbz" if self.recursive else "*.cbz"
        for cbz_file in sorted(self.path.glob(pattern)):
            if self._cancelled:
                break
            if cbz_file.is_file():
                self.progress.emit(str(cbz_file.name))
                comics.append(read_cbz_metadata(cbz_file))
        self.finished.emit(comics)

    def cancel(self):
        self._cancelled = True


class EnrichWorker(QThread):
    progress = Signal(int, int)
    finished = Signal(list, bool)
    error = Signal(str)

    def __init__(self, comics: list[Comic], api_key: str, cache_enabled: bool = True):
        super().__init__()
        self.comics = comics
        self.api_key = api_key
        self.cache_enabled = cache_enabled
        self._cancelled = False

    def run(self):
        client = ComicVineClient(self.api_key, cache_enabled=self.cache_enabled)
        errors = False
        total = len(self.comics)
        for i, comic in enumerate(self.comics):
            if self._cancelled:
                break
            try:
                self._enrich_comic(comic, client)
            except InvalidAPIKeyError:
                self.error.emit("Invalid API key"); errors = True; break
            except RateLimitError:
                self.error.emit("Rate limit exceeded — try again later"); errors = True; break
            except ComicVineError as exc:
                self.error.emit(f"API error: {exc}"); errors = True
            self.progress.emit(i + 1, total)
        self.finished.emit(self.comics, errors)

    def _enrich_comic(self, comic, client):
        if comic.has_cv_ids:
            return
        if comic.cv_issue_id:
            issue = client.get_issue(comic.cv_issue_id)
            if issue.series_id and not comic.cv_series_id:
                comic.cv_series_id = issue.series_id
            self._apply_issue_data(comic, issue); return
        for url in comic.web_links:
            ids = extract_comicvine_ids(url)
            if ids.get("issue_id"):
                comic.cv_issue_id = ids["issue_id"]
                self._fetch_and_apply_issue(comic, client, ids["issue_id"]); return
            if ids.get("series_id") and not comic.cv_series_id:
                comic.cv_series_id = ids["series_id"]
        if comic.cv_series_id or not (comic.series_name and comic.issue_number):
            return
        results = client.search_issue(f"{comic.series_name} #{comic.issue_number}")
        if results:
            issue = results[0]; comic.cv_issue_id = issue.id
            if issue.series_id: comic.cv_series_id = issue.series_id
            self._apply_issue_data(comic, issue)

    def _fetch_and_apply_issue(self, comic, client, issue_id):
        issue = client.get_issue(issue_id)
        if issue.series_id and not comic.cv_series_id:
            comic.cv_series_id = issue.series_id
        self._apply_issue_data(comic, issue)

    def _apply_issue_data(self, comic, issue):
        """Persist normalized Comic Vine data without replacing user metadata."""
        comic.cv_metadata = issue
        if issue.id and not comic.cv_issue_id:
            comic.cv_issue_id = issue.id
        if issue.series_id and not comic.cv_series_id:
            comic.cv_series_id = issue.series_id
        if not comic.series_name and issue.series_name:
            comic.series_name = issue.series_name
        if not comic.volume and issue.volume:
            comic.volume = issue.volume
        if not comic.issue_number and issue.issue_number:
            comic.issue_number = issue.issue_number

        cover_date = (issue.cover_date or "").split("-")
        date_fields = ("year", "month", "day")
        for field, value in zip(date_fields, cover_date):
            if not getattr(comic, field) and value:
                setattr(comic, field, value)

        if issue.web_url:
            web_url = self._normalize_issue_url(issue.web_url, comic.cv_issue_id)
            if web_url and web_url not in comic.web_links:
                comic.web_links.append(web_url)

    @staticmethod
    def _normalize_issue_url(web_url, issue_id):
        """Keep the persisted URL aligned with the comic's canonical issue ID."""
        if not web_url or not issue_id:
            return web_url
        normalized_id = str(issue_id)
        return re.sub(
            r"(/4000-)\d+(?=/|$)",
            lambda match: f"{match.group(1)}{normalized_id}",
            web_url,
            count=1,
        )

    def cancel(self):
        self._cancelled = True
