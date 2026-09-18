"""Unified read/write entry points for local CBZ and CBR comic archives."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from comicdesk.models import Comic
from comicdesk.services.cbr_reader import read_cbr_metadata
from comicdesk.services.cbr_writer import write_cbr_as_cbz_metadata
from comicdesk.services.cbz_reader import read_cbz_metadata
from comicdesk.services.cbz_writer import CbzWriteError, write_cbz_metadata

LOCAL_COMIC_SUFFIXES = (".cbz", ".cbr")

ComicArchiveWriteError = CbzWriteError


def iter_comic_files(folder_path: Path, recursive: bool = True) -> Iterator[Path]:
    """Yield local comic archive paths under *folder_path* in sorted order."""
    folder_path = Path(folder_path)
    patterns = (
        ("**/*.cbz", "**/*.cbr") if recursive else ("*.cbz", "*.cbr")
    )
    seen: set[Path] = set()
    paths: list[Path] = []
    for pattern in patterns:
        for candidate in folder_path.glob(pattern):
            if candidate.is_file():
                resolved = candidate.resolve()
                if resolved not in seen:
                    seen.add(resolved)
                    paths.append(candidate)
    for path in sorted(paths, key=lambda p: str(p).casefold()):
        yield path


def read_comic_metadata(path: Path) -> Comic:
    """Read metadata from a CBZ or CBR file."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".cbz":
        return read_cbz_metadata(path)
    if suffix == ".cbr":
        return read_cbr_metadata(path)
    return Comic(path=path)


def write_comic_metadata(comic: Comic) -> Path:
    """Persist metadata; CBR inputs are converted to CBZ on disk."""
    path = Path(comic.path)
    suffix = path.suffix.lower()
    if suffix == ".cbz":
        return write_cbz_metadata(comic)
    if suffix == ".cbr":
        return write_cbr_as_cbz_metadata(comic)
    raise CbzWriteError(f"Unsupported comic archive type: {path}")
