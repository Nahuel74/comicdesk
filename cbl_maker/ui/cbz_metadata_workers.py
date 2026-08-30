"""Qt workers used by the single-CBZ metadata editor."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import logging

from PySide6.QtCore import QThread, Signal

from cbl_maker.services.cbz_writer import write_cbz_metadata
from cbl_maker.services.comicvine_api import (
    ComicVineClient,
    ComicVineError,
    InvalidAPIKeyError,
    RateLimitError,
)
from cbl_maker.services.identification import identify_comic

logger = logging.getLogger(__name__)


def _api_error_message(error: Exception) -> str:
    if isinstance(error, InvalidAPIKeyError):
        return "Comic Vine API key is invalid or empty"
    if isinstance(error, RateLimitError):
        return "Comic Vine rate limit exceeded; try again later"
    if isinstance(error, ComicVineError):
        return f"Comic Vine API error: {error}"
    return f"Comic Vine request failed: {error}"


class MetadataSearchWorker(QThread):
    """Identify a snapshot without ever mutating the editor's original."""

    finished = Signal(object)
    error = Signal(str)

    def __init__(self, comic, api_key: str, cache_enabled: bool = True,
                 token: int = 0, force_refresh: bool = False):
        super().__init__()
        self.comic = deepcopy(comic)
        self.api_key = str(api_key or "").strip()
        self.cache_enabled = bool(cache_enabled)
        self.token = token
        self.force_refresh = bool(force_refresh)
        self._cancelled = False

    def run(self):
        if self._cancelled:
            return
        if not self.api_key:
            self.error.emit("Comic Vine API key is empty")
            return
        try:
            # Disabling the cache for an explicit refresh retains the normal
            # configured behavior for regular searches.
            client = ComicVineClient(
                self.api_key,
                cache_enabled=self.cache_enabled and not self.force_refresh,
            )
            result = identify_comic(self.comic, client)
            if not self._cancelled:
                self.finished.emit(result)
        except Exception as exc:  # workers must report recoverable failures
            logger.exception("metadata_search_failed error_type=%s", type(exc).__name__)
            if not self._cancelled:
                self.error.emit(_api_error_message(exc))

    def cancel(self):
        self._cancelled = True


class MetadataWriteWorker(QThread):
    """Write a frozen draft to disk in a thread."""

    finished = Signal(object)
    error = Signal(str)

    def __init__(self, comic, token: int = 0, path=None):
        super().__init__()
        self.comic = deepcopy(comic)
        self.token = token
        raw_path = path if path is not None else getattr(self.comic, "path", None)
        self.path = Path(raw_path) if raw_path else Path()
        self.comic.path = self.path
        self._cancelled = False

    def run(self):
        if self._cancelled:
            return
        try:
            saved_path = write_cbz_metadata(self.comic)
            if not self._cancelled:
                self.finished.emit(saved_path)
        except Exception as exc:  # includes empty/imported CBL paths
            logger.exception("metadata_write_failed error_type=%s", type(exc).__name__)
            if not self._cancelled:
                self.error.emit(f"Unable to save CBZ metadata: {exc}")

    def cancel(self):
        self._cancelled = True


class MetadataHydrateWorker(QThread):
    """Fetch complete Comic Vine details for a selected candidate."""

    finished = Signal(object)
    error = Signal(str)

    def __init__(self, candidate, api_key: str, cache_enabled: bool = True,
                 token: int = 0):
        super().__init__()
        self.candidate = deepcopy(candidate)
        self.api_key = str(api_key or "").strip()
        self.cache_enabled = bool(cache_enabled)
        self.token = token
        self._cancelled = False

    def run(self):
        if self._cancelled:
            return
        if not self.api_key:
            self.error.emit("Comic Vine API key is empty")
            return
        try:
            client = ComicVineClient(self.api_key, cache_enabled=self.cache_enabled)
            hydrated = client.get_issue(self.candidate.id)
            if not self._cancelled:
                self.finished.emit(hydrated)
        except Exception as exc:
            logger.exception("metadata_hydrate_failed error_type=%s", type(exc).__name__)
            if not self._cancelled:
                self.error.emit(_api_error_message(exc))

    def cancel(self):
        self._cancelled = True


# Short names make the module convenient to integrate without hiding the
# descriptive public classes above.
SearchWorker = MetadataSearchWorker
WriteWorker = MetadataWriteWorker
HydrateWorker = MetadataHydrateWorker
SearchMetadataWorker = MetadataSearchWorker
WriteMetadataWorker = MetadataWriteWorker
HydrateMetadataWorker = MetadataHydrateWorker
ComicMetadataSearchWorker = MetadataSearchWorker
ComicMetadataWriteWorker = MetadataWriteWorker
ComicMetadataHydrateWorker = MetadataHydrateWorker
CBZMetadataSearchWorker = MetadataSearchWorker
CBZMetadataWriteWorker = MetadataWriteWorker
CBZMetadataHydrateWorker = MetadataHydrateWorker
