"""Persistent wishlist for CBL references missing from the local library."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from cbl_maker.config import CONFIG_DIR
from cbl_maker.models import CBLBook, Comic, ComicVineMetadata
from cbl_maker.services.cbl_reader import book_dedupe_key, reconcile_cbl

logger = logging.getLogger(__name__)

WISHLIST_FILE = CONFIG_DIR / "wishlist.json"


@dataclass
class WishlistAddResult:
    """Outcome of adding books to the wishlist."""
    added: int = 0
    skipped_duplicates: int = 0


def _serialize_metadata(metadata: ComicVineMetadata | None) -> dict | None:
    if metadata is None:
        return None
    return {
        "id": metadata.id,
        "series_id": metadata.series_id,
        "series_name": metadata.series_name,
        "volume": metadata.volume,
        "issue_number": metadata.issue_number,
        "cover_date": metadata.cover_date,
        "web_url": metadata.web_url,
    }


def _deserialize_metadata(data: dict | None) -> ComicVineMetadata | None:
    if not data:
        return None
    return ComicVineMetadata(
        id=str(data.get("id", "")),
        series_id=str(data.get("series_id", "")),
        series_name=str(data.get("series_name", "")),
        volume=str(data.get("volume", "")),
        issue_number=str(data.get("issue_number", "")),
        cover_date=str(data.get("cover_date", "")),
        web_url=str(data.get("web_url", "")),
    )


def _serialize_book(book: CBLBook) -> dict:
    payload = {
        "series_name": book.series_name,
        "volume": book.volume,
        "issue_number": book.issue_number,
        "cv_series_id": book.cv_series_id,
        "cv_issue_id": book.cv_issue_id,
        "position": book.position,
    }
    metadata = _serialize_metadata(book.cv_metadata)
    if metadata is not None:
        payload["cv_metadata"] = metadata
    return payload


def _deserialize_book(data: dict) -> CBLBook:
    return CBLBook(
        series_name=str(data.get("series_name", "")),
        volume=str(data.get("volume", "")),
        issue_number=str(data.get("issue_number", "")),
        cv_series_id=data.get("cv_series_id") or None,
        cv_issue_id=data.get("cv_issue_id") or None,
        position=int(data.get("position", 0)),
        cv_metadata=_deserialize_metadata(data.get("cv_metadata")),
    )


class WishlistManager:
    """In-memory wishlist with atomic JSON persistence."""

    def __init__(
        self,
        path: Path | None = None,
        on_changed: Callable[[], None] | None = None,
    ) -> None:
        self._path = path or WISHLIST_FILE
        self._on_changed = on_changed
        self._items: list[CBLBook] = []
        self.load()

    @property
    def path(self) -> Path:
        return self._path

    def items(self) -> list[CBLBook]:
        return list(self._items)

    def add_books(self, books: Iterable[CBLBook]) -> WishlistAddResult:
        result = WishlistAddResult()
        seen = {book_dedupe_key(book) for book in self._items}
        changed = False
        for book in books:
            key = book_dedupe_key(book)
            if key in seen:
                result.skipped_duplicates += 1
                continue
            seen.add(key)
            self._items.append(book)
            result.added += 1
            changed = True
        if changed:
            self.save()
            self._notify_changed()
        return result

    def remove_books(self, books: Iterable[CBLBook]) -> int:
        keys = {book_dedupe_key(book) for book in books}
        if not keys:
            return 0
        initial = len(self._items)
        self._items = [book for book in self._items if book_dedupe_key(book) not in keys]
        removed = initial - len(self._items)
        if removed:
            self.save()
            self._notify_changed()
        return removed

    def clear(self) -> None:
        if not self._items:
            return
        self._items.clear()
        self.save()
        self._notify_changed()

    def reconcile_with_library(self, comics: Iterable[Comic]) -> int:
        """Remove wishlist items that now match comics in the local library."""
        if not self._items:
            return 0
        result = reconcile_cbl(self._items, comics)
        initial = len(self._items)
        self._items = result.missing_files
        removed = initial - len(self._items)
        if removed:
            self.save()
            self._notify_changed()
        return removed

    def set_on_changed(self, callback: Callable[[], None] | None) -> None:
        self._on_changed = callback

    def load(self) -> None:
        if not self._path.exists():
            self._items = []
            return
        try:
            with open(self._path, encoding="utf-8") as handle:
                data = json.load(handle)
            if not isinstance(data, list):
                raise TypeError("wishlist root must be a JSON array")
            self._items = [_deserialize_book(item) for item in data if isinstance(item, dict)]
        except (json.JSONDecodeError, IOError, OSError, TypeError, ValueError) as exc:
            logger.warning("Failed to load wishlist: %s", exc)
            self._items = []

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(dir=self._path.parent, suffix=".json")
        tmp_path = Path(name)
        os.close(fd)
        try:
            payload = [_serialize_book(book) for book in self._items]
            with open(tmp_path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)
            os.replace(tmp_path, self._path)
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise

    def _notify_changed(self) -> None:
        if self._on_changed is not None:
            self._on_changed()
