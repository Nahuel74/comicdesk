"""Injectable CBR (RAR) read backend for ComicInfo and page extraction."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Protocol

COMICINFO_NAME = "ComicInfo.xml"

_MISSING_TOOL_MESSAGE = (
    "Cannot read CBR archives: install unrar or unrar-free on your PATH, "
    "or set UNRAR_TOOL to the unrar binary. "
    "Password-protected or unsupported RAR5 archives may also fail."
)


class CbrReadError(Exception):
    """Raised when a CBR cannot be opened or read."""


class CbrArchive(Protocol):
    def namelist(self) -> list[str]: ...
    def read(self, name: str) -> bytes: ...
    def close(self) -> None: ...


class _InMemoryCbrArchive:
    """Test double backed by a member name → bytes map."""

    def __init__(self, members: dict[str, bytes]):
        self._members = dict(members)
        self._order = list(members.keys())

    def namelist(self) -> list[str]:
        return list(self._order)

    def read(self, name: str) -> bytes:
        if name not in self._members:
            raise KeyError(name)
        return self._members[name]

    def close(self) -> None:
        return None


_test_opener: object | None = None


def set_cbr_opener_for_tests(opener) -> None:
    """Replace the default opener (callable path -> CbrArchive context) in tests."""
    global _test_opener
    _test_opener = opener


def reset_cbr_opener_for_tests() -> None:
    global _test_opener
    _test_opener = None


def comicinfo_member_name(names: list[str]) -> str | None:
    for name in names:
        if name.lower() == COMICINFO_NAME.lower():
            return name
    return None


def is_directory_member_name(name: str) -> bool:
    """True for RAR/ZIP folder entries (no file payload)."""
    if not name or name in {".", ".."}:
        return True
    return name.endswith(("/", "\\"))


def iter_archive_file_members(archive: CbrArchive) -> Iterator[str]:
    """Yield member paths that hold file data (skip RAR directory entries)."""
    if isinstance(archive, _RarfileArchive):
        for info in archive._rf.infolist():
            if info.isdir():
                continue
            yield info.filename
        return
    for name in archive.namelist():
        if is_directory_member_name(name):
            continue
        yield name


@contextmanager
def open_cbr(path: Path) -> Iterator[CbrArchive]:
    """Open a CBR for reading. Uses rarfile + a system unrar/unar when available."""
    if _test_opener is not None:
        archive = _test_opener(path)
        try:
            yield archive
        finally:
            archive.close()
        return

    try:
        import rarfile
    except ImportError as exc:
        raise CbrReadError(
            "Cannot read CBR archives: install the Python package 'rarfile' "
            f"({exc})."
        ) from exc

    try:
        rf = rarfile.RarFile(path)
    except rarfile.RarCannotExec as exc:
        raise CbrReadError(_MISSING_TOOL_MESSAGE) from exc
    except rarfile.Error as exc:
        raise CbrReadError(f"Not a valid CBR archive: {path} ({exc})") from exc
    except OSError as exc:
        raise CbrReadError(f"Cannot open CBR: {path} ({exc})") from exc

    wrapper = _RarfileArchive(rf)
    try:
        yield wrapper
    finally:
        wrapper.close()


class _RarfileArchive:
    def __init__(self, rf) -> None:
        self._rf = rf

    def namelist(self) -> list[str]:
        return list(self._rf.namelist())

    def read(self, name: str) -> bytes:
        return self._rf.read(name)

    def close(self) -> None:
        self._rf.close()


@contextmanager
def in_memory_cbr(members: dict[str, bytes]):
    """Context manager factory for tests."""
    archive = _InMemoryCbrArchive(members)
    try:
        yield archive
    finally:
        archive.close()
