"""Persistent mtime/size cache for local comic metadata reads during library scans."""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from comicdesk.config import CONFIG_DIR
from comicdesk.models import Comic

logger = logging.getLogger(__name__)

CACHE_DIR = CONFIG_DIR / "cache"
CACHE_FILE = CACHE_DIR / "scan_metadata.json"

_lock = threading.Lock()
_loaded = False
_entries: dict[str, dict[str, Any]] = {}

_COMIC_FIELDS = (
    "title",
    "series_name",
    "volume",
    "issue_number",
    "year",
    "month",
    "day",
    "web_links",
    "cv_series_id",
    "cv_issue_id",
    "alternate_series",
    "alternate_number",
    "alternate_count",
    "count",
    "story_arc",
    "story_arc_number",
    "summary",
    "notes",
    "writer",
    "penciller",
    "inker",
    "colorist",
    "letterer",
    "cover_artist",
    "editor",
    "translator",
    "publisher",
    "imprint",
    "genre",
    "tags",
    "page_count",
    "language_iso",
    "format",
    "black_and_white",
    "manga",
    "characters",
    "teams",
    "locations",
    "scan_information",
    "age_rating",
    "community_rating",
    "main_character_or_team",
    "review",
    "series_group",
    "gtin",
    "comicinfo_unknown",
)


def _ensure_loaded() -> None:
    global _loaded
    if _loaded:
        return
    with _lock:
        if _loaded:
            return
        _entries.clear()
        if CACHE_FILE.exists():
            try:
                with open(CACHE_FILE, encoding="utf-8") as handle:
                    data = json.load(handle)
                if isinstance(data, dict):
                    _entries.update(data)
            except (json.JSONDecodeError, OSError, TypeError):
                _entries.clear()
        _loaded = True


def _file_stat_key(path: Path) -> tuple[str, int, int] | None:
    try:
        stat = path.resolve().stat()
        return str(path.resolve()), stat.st_mtime_ns, stat.st_size
    except OSError:
        return None


def _serialize_unknown_elements(items: list[Any]) -> list[str]:
    encoded: list[str] = []
    for item in items:
        if isinstance(item, ET.Element):
            encoded.append(ET.tostring(item, encoding="unicode"))
    return encoded


def _deserialize_unknown_elements(items: list[Any]) -> list[Any]:
    restored: list[Any] = []
    for item in items or []:
        if not isinstance(item, str):
            continue
        try:
            restored.append(ET.fromstring(item))
        except ET.ParseError:
            continue
    return restored


def _comic_to_payload(comic: Comic) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for field in _COMIC_FIELDS:
        value = getattr(comic, field)
        if field == "web_links":
            payload[field] = list(value)
        elif field == "comicinfo_unknown":
            payload[field] = _serialize_unknown_elements(list(value))
        else:
            payload[field] = value
    return payload


def _comic_from_payload(path: Path, payload: dict[str, Any]) -> Comic:
    kwargs: dict[str, Any] = {"path": path}
    for field in _COMIC_FIELDS:
        if field not in payload:
            continue
        value = payload[field]
        if field == "web_links":
            kwargs[field] = list(value or [])
        elif field == "comicinfo_unknown":
            kwargs[field] = _deserialize_unknown_elements(list(value or []))
        else:
            kwargs[field] = value
    return Comic(**kwargs)


def get_cached_comic(path: Path) -> Comic | None:
    """Return a cached Comic when path mtime and size still match."""
    _ensure_loaded()
    stat_key = _file_stat_key(path)
    if stat_key is None:
        return None
    resolved, mtime_ns, size = stat_key
    with _lock:
        entry = _entries.get(resolved)
        if not entry:
            return None
        if entry.get("mtime_ns") != mtime_ns or entry.get("size") != size:
            return None
        fields = entry.get("fields")
        if not isinstance(fields, dict):
            return None
    return _comic_from_payload(path, fields)


def store_cached_comic(path: Path, comic: Comic) -> None:
    """Remember parsed metadata for *path* (in-memory; flushed after scans)."""
    stat_key = _file_stat_key(path)
    if stat_key is None:
        return
    resolved, mtime_ns, size = stat_key
    with _lock:
        _entries[resolved] = {
            "mtime_ns": mtime_ns,
            "size": size,
            "fields": _comic_to_payload(comic),
        }


def flush_scan_metadata_cache() -> None:
    """Persist the in-memory cache to disk using an atomic replace."""
    _ensure_loaded()
    with _lock:
        snapshot = dict(_entries)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    tmp_path = None
    try:
        fd, name = tempfile.mkstemp(dir=CACHE_DIR, suffix=".json")
        os.close(fd)
        tmp_path = Path(name)
        with open(tmp_path, "w", encoding="utf-8") as handle:
            json.dump(snapshot, handle)
        os.replace(tmp_path, CACHE_FILE)
    except (OSError, TypeError, ValueError) as exc:
        logger.warning("Failed to save scan metadata cache: %s", exc)
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)


def reset_scan_metadata_cache_for_tests() -> None:
    """Clear the cache (tests only)."""
    global _loaded
    with _lock:
        _entries.clear()
        _loaded = True
