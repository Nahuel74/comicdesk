"""Background workers for scanning and Comic Vine enrichment."""

from pathlib import Path
import re
from PySide6.QtCore import QThread, Signal

from cbl_maker.models import Comic
from cbl_maker.services.cbz_reader import read_cbz_metadata
from cbl_maker.services.cbz_writer import write_cbz_metadata
from cbl_maker.services.comicvine_api import (
    ComicVineClient, ComicVineError, RateLimitError, InvalidAPIKeyError,
)
from cbl_maker.services.identification import apply_issue_to_comic
from cbl_maker.utils.url_parser import extract_comicvine_ids
from cbl_maker.models import ComicVineVolume
from cbl_maker.services.comicvine_mapping import apply_volume_metadata


class ScanWorker(QThread):
    finished = Signal(list)
    progress = Signal(str)
    error = Signal(str)

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
                try:
                    comics.append(read_cbz_metadata(cbz_file))
                except Exception as exc:
                    self.error.emit(f"Unable to read {cbz_file.name}: {exc}")
        self.finished.emit(comics)

    def cancel(self):
        self._cancelled = True


class EnrichWorker(QThread):
    progress = Signal(int, int)
    finished = Signal(list, bool)
    error = Signal(str)

    def __init__(self, comics: list[Comic], api_key: str, cache_enabled: bool = True,
                 batch_update: bool = False):
        super().__init__()
        self.comics = comics
        self.api_key = api_key
        self.cache_enabled = cache_enabled
        self.batch_update = batch_update
        self._cancelled = False

    def run(self):
        errors = False
        total = len(self.comics)
        try:
            client = ComicVineClient(self.api_key, cache_enabled=self.cache_enabled)
            self._active_client = client
        except Exception as exc:
            self.error.emit(f"API error: {exc}")
            self.finished.emit(self.comics, True)
            return
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
            except Exception as exc:
                self.error.emit(f"API error: {exc}"); errors = True
            self.progress.emit(i + 1, total)
        self.finished.emit(self.comics, errors)

    def _enrich_comic(self, comic, client):
        if comic.has_cv_ids and not self.batch_update:
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
        """Apply the complete Comic Vine issue payload to the local comic."""
        apply_issue_to_comic(comic, issue, overwrite=self.batch_update)
        if not self.batch_update and issue.web_url:
            normalized = self._normalize_issue_url(issue.web_url, comic.cv_issue_id)
            if normalized != issue.web_url and issue.web_url in comic.web_links:
                comic.web_links.remove(issue.web_url)
                comic.web_links.append(normalized)
        if self.batch_update and comic.path and str(comic.path) != ".":
            write_cbz_metadata(comic)

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
