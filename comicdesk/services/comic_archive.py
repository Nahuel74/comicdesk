"""Unified read/write entry points for local CBZ and CBR comic archives."""

from __future__ import annotations

import os
import threading
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from comicdesk.models import Comic
from comicdesk.services.cbr_reader import read_cbr_metadata
from comicdesk.services.cbr_writer import write_cbr_as_cbz_metadata
from comicdesk.services.cbz_reader import read_cbz_metadata
from comicdesk.services.cbz_writer import CbzWriteError, write_cbz_metadata
from comicdesk.services.scan_metadata_cache import (
    flush_scan_metadata_cache,
    get_cached_comic,
    store_cached_comic,
)

LOCAL_COMIC_SUFFIXES = (".cbz", ".cbr")
_SCAN_CHUNK_SIZE = 64
_PARALLEL_MIN_FILES = 48

ComicArchiveWriteError = CbzWriteError


def _default_max_workers() -> int:
    return min(32, (os.cpu_count() or 1) + 4)


def iter_comic_files(folder_path: Path, recursive: bool = True) -> Iterator[Path]:
    """Yield local comic archive paths under *folder_path* in sorted order."""
    folder_path = Path(folder_path)
    suffixes = {suffix.lower() for suffix in LOCAL_COMIC_SUFFIXES}
    seen: set[Path] = set()
    paths: list[Path] = []

    def consider(candidate: Path) -> None:
        if not candidate.is_file():
            return
        if candidate.suffix.lower() not in suffixes:
            return
        resolved = candidate.resolve()
        if resolved not in seen:
            seen.add(resolved)
            paths.append(candidate)

    if recursive:
        for candidate in folder_path.rglob("*"):
            consider(candidate)
    else:
        for candidate in folder_path.iterdir():
            consider(candidate)

    for path in sorted(paths, key=lambda p: str(p).casefold()):
        yield path


def read_comic_metadata(path: Path) -> Comic:
    """Read metadata from a CBZ or CBR file."""
    path = Path(path)
    cached = get_cached_comic(path)
    if cached is not None:
        return cached

    suffix = path.suffix.lower()
    if suffix == ".cbz":
        comic = read_cbz_metadata(path)
    elif suffix == ".cbr":
        comic = read_cbr_metadata(path)
    else:
        comic = Comic(path=path)

    store_cached_comic(path, comic)
    return comic


def read_comic_metadata_fresh(path: Path) -> Comic:
    """Read ComicInfo from disk without using the scan metadata cache."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".cbz":
        return read_cbz_metadata(path)
    if suffix == ".cbr":
        return read_cbr_metadata(path)
    return Comic(path=path)


def _read_comic_for_scan(path: Path) -> tuple[Comic | None, str | None]:
    try:
        return read_comic_metadata(path), None
    except Exception as exc:
        return None, f"Unable to read {path.name}: {exc}"


def scan_comics(
    folder_path: Path,
    recursive: bool = True,
    *,
    max_workers: int | None = None,
    progress: Callable[[int, int, str], None] | None = None,
    on_error: Callable[[str], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> list[Comic]:
    """Enumerate comics under *folder_path* and read metadata (parallel by default)."""
    paths = list(iter_comic_files(folder_path, recursive))
    if not paths:
        return []

    workers = max_workers if max_workers is not None else _default_max_workers()
    if len(paths) < _PARALLEL_MIN_FILES:
        workers = 1
    comics: list[Comic] = []
    total = len(paths)
    if progress:
        progress(0, total, "")

    def consume_chunk(
        chunk: list[Path], chunk_start: int, executor: ThreadPoolExecutor | None
    ) -> None:
        if workers <= 1:
            results = [_read_comic_for_scan(path) for path in chunk]
        else:
            assert executor is not None
            results = list(executor.map(_read_comic_for_scan, chunk))
        for offset, (path, (comic, error)) in enumerate(zip(chunk, results)):
            if error:
                if on_error:
                    on_error(error)
            elif comic is not None:
                comics.append(comic)
            if progress:
                progress(chunk_start + offset + 1, total, path.name)

    chunk_ranges = range(0, len(paths), _SCAN_CHUNK_SIZE)
    if workers <= 1:
        for chunk_start in chunk_ranges:
            if cancelled and cancelled():
                break
            chunk = paths[chunk_start : chunk_start + _SCAN_CHUNK_SIZE]
            consume_chunk(chunk, chunk_start, None)
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            for chunk_start in chunk_ranges:
                if cancelled and cancelled():
                    break
                chunk = paths[chunk_start : chunk_start + _SCAN_CHUNK_SIZE]
                consume_chunk(chunk, chunk_start, executor)

    threading.Thread(target=flush_scan_metadata_cache, daemon=True).start()
    return comics


def write_comic_metadata(comic: Comic) -> Path:
    """Persist metadata; CBR inputs are converted to CBZ on disk."""
    path = Path(comic.path)
    suffix = path.suffix.lower()
    if suffix == ".cbz":
        return write_cbz_metadata(comic)
    if suffix == ".cbr":
        return write_cbr_as_cbz_metadata(comic)
    raise CbzWriteError(f"Unsupported comic archive type: {path}")
