"""List and remove image members from local comic archives."""

from __future__ import annotations

import os
import re
import stat
import tempfile
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path, PurePosixPath

from comicdesk.services.cbr_backend import (
    CbrReadError,
    COMICINFO_NAME,
    comicinfo_member_name,
    iter_archive_file_members,
    open_cbr,
)
from comicdesk.services.cbz_writer import (
    CbzWriteError,
    is_zip_comic_archive,
    parse_comicinfo_root,
)
from comicdesk.services.comicinfo import local_name

_IMAGE_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"})
_COMICINFO_LOWER = COMICINFO_NAME.lower()
_JUNK_SUBSTRINGS = (
    "water",
    "credit",
    "advert",
    "bonus",
    "readme",
    "scaninfo",
    "sample",
)


def is_image_page_member(name: str) -> bool:
    """True when *name* is a listable/deletable image page (not ComicInfo or other)."""
    if not name or name.endswith(("/", "\\")):
        return False
    if name.lower() == _COMICINFO_LOWER:
        return False
    return Path(name).suffix.casefold() in _IMAGE_SUFFIXES


def list_image_pages(path: Path) -> list[str]:
    """Return image member names in archive order."""
    path = Path(path)
    if not path.is_file():
        raise CbzWriteError(f"Comic archive not found: {path}")
    suffix = path.suffix.casefold()
    if suffix == ".cbz":
        return _list_image_pages_cbz(path)
    if suffix == ".cbr":
        if is_zip_comic_archive(path):
            return _list_image_pages_cbz(path)
        return _list_image_pages_cbr(path)
    raise CbzWriteError(f"Unsupported comic archive type: {path}")


def read_image_member_bytes(path: Path, member_name: str) -> bytes:
    """Read raw bytes for one image member from a CBZ or CBR archive."""
    path = Path(path)
    if not path.is_file():
        raise CbzWriteError(f"Comic archive not found: {path}")
    if not is_image_page_member(member_name):
        raise CbzWriteError(f"Not an image page member: {member_name}")

    suffix = path.suffix.casefold()
    try:
        if suffix == ".cbz" or (suffix == ".cbr" and is_zip_comic_archive(path)):
            with zipfile.ZipFile(path, "r") as archive:
                if member_name not in archive.namelist():
                    raise CbzWriteError(f"Archive member not found: {member_name}")
                return archive.read(member_name)
        with open_cbr(path) as archive:
            return archive.read(member_name)
    except CbrReadError as exc:
        raise CbzWriteError(str(exc)) from exc
    except (zipfile.BadZipFile, OSError, KeyError) as exc:
        raise CbzWriteError(f"Unable to read {member_name}: {exc}") from exc


def detect_extraneous_image_pages(page_names: list[str]) -> list[str]:
    """Suggest image members to remove using filename heuristics only.

    Keeps pages that look numbered, use common story/cover naming, or match the
    dominant digit-normalized stem pattern among the archive's images. Flags junk
    substrings (water, credit, …) and ``z*`` prefixes, plus names with no logical
    criterion. Order matches *page_names*.
    """
    if not page_names:
        return []
    dominant = _dominant_stem_pattern(page_names)
    extras: list[str] = []
    for name in page_names:
        if _is_junk_filename(name):
            extras.append(name)
        elif not _has_logical_page_criterion(name, dominant):
            extras.append(name)
    return extras


def _normalize_stem_pattern(stem: str) -> str:
    return re.sub(r"\d+", "#", stem)


def _dominant_stem_pattern(page_names: list[str]) -> str | None:
    if len(page_names) < 2:
        return None
    patterns = [_normalize_stem_pattern(Path(name).stem) for name in page_names]
    pattern, count = Counter(patterns).most_common(1)[0]
    if count >= 2:
        return pattern
    return None


def _has_numbering_criterion(stem: str) -> bool:
    if re.search(r"\bpage\s*\d+", stem, re.IGNORECASE):
        return True
    if re.search(r"\bp\d+\b", stem, re.IGNORECASE):
        return True
    if re.search(r"\d{3}-\d{3}", stem):
        return True
    if re.search(r"-\d+\b", stem):
        return True
    if re.fullmatch(r"\d+", stem):
        return True
    if re.search(r"\d{2,}", stem):
        return True
    return False


def _has_legit_keyword(stem: str) -> bool:
    lower = stem.casefold()
    if "cover" in lower:
        return True
    if re.search(r"\bpage\b", lower):
        return True
    if re.search(r"\bp\d+\b", lower):
        return True
    return False


def _has_logical_page_criterion(name: str, dominant_pattern: str | None) -> bool:
    stem = Path(name).stem
    if _has_numbering_criterion(stem):
        return True
    if _has_legit_keyword(stem):
        return True
    if dominant_pattern is not None:
        if _normalize_stem_pattern(stem) == dominant_pattern:
            return True
    return False


def _is_junk_filename(name: str) -> bool:
    stem = Path(name).stem
    lower = stem.casefold()
    if lower.startswith("z") and len(lower) > 1:
        return True
    return any(token in lower for token in _JUNK_SUBSTRINGS)


def rename_image_members(path: Path, renames: dict[str, str]) -> Path:
    """Rename image members inside an archive atomically; return path written (.cbz)."""
    path = Path(path)
    if not path.is_file():
        raise CbzWriteError(f"Comic archive not found: {path}")
    if not renames:
        raise CbzWriteError("No page renames specified")

    archive_names = set(_all_member_names(path))
    current_images = list_image_pages(path)
    image_set = set(current_images)

    for old_name, new_name in renames.items():
        if old_name not in archive_names:
            raise CbzWriteError(f"Archive member not found: {old_name}")
        if not is_image_page_member(old_name):
            raise CbzWriteError(f"Not a renameable image page: {old_name}")
        if old_name not in image_set:
            raise CbzWriteError(f"Not a renameable image page: {old_name}")
        if not is_image_page_member(new_name):
            raise CbzWriteError(f"Invalid rename target: {new_name}")
        if not _is_root_member_name(new_name):
            raise CbzWriteError(
                f"Renamed page must be at archive root (no folders): {new_name}"
            )
        if old_name == new_name:
            continue

    active = {k: v for k, v in renames.items() if k != v}
    if not active:
        return path

    targets = list(active.values())
    if len(set(targets)) != len(targets):
        raise CbzWriteError("Duplicate target names in page rename batch")
    for target in targets:
        if target in archive_names and target not in active:
            raise CbzWriteError(f"Target name already exists in archive: {target}")

    suffix = path.suffix.casefold()
    if suffix == ".cbz":
        return _rename_in_cbz(path, active)
    if suffix == ".cbr":
        if is_zip_comic_archive(path):
            return _rename_in_cbz(path, active)
        return _rename_in_cbr(path, active)
    raise CbzWriteError(f"Unsupported comic archive type: {path}")


def remove_image_pages(path: Path, names: list[str] | set[str]) -> Path:
    """Remove *names* from the archive atomically; return the path written (.cbz)."""
    path = Path(path)
    if not path.is_file():
        raise CbzWriteError(f"Comic archive not found: {path}")
    omit = set(names)
    if not omit:
        raise CbzWriteError("No pages selected for removal")

    current_images = list_image_pages(path)
    archive_names = set(_all_member_names(path))
    for name in omit:
        if name not in archive_names:
            raise CbzWriteError(f"Archive member not found: {name}")
        if not is_image_page_member(name):
            raise CbzWriteError(f"Not a removable image page: {name}")

    remaining = [name for name in current_images if name not in omit]
    if not remaining:
        raise CbzWriteError("At least one image page must remain in the archive")

    suffix = path.suffix.casefold()
    if suffix == ".cbz":
        return _remove_from_cbz(path, omit, len(remaining))
    if suffix == ".cbr":
        if is_zip_comic_archive(path):
            return _remove_from_cbz(path, omit, len(remaining))
        return _remove_from_cbr(path, omit, len(remaining))
    raise CbzWriteError(f"Unsupported comic archive type: {path}")


def _all_member_names(path: Path) -> list[str]:
    suffix = path.suffix.casefold()
    if suffix == ".cbz" or is_zip_comic_archive(path):
        with zipfile.ZipFile(path, "r") as archive:
            return list(archive.namelist())
    with open_cbr(path) as archive:
        return list(iter_archive_file_members(archive))


def _list_image_pages_cbz(path: Path) -> list[str]:
    try:
        with zipfile.ZipFile(path, "r") as archive:
            return [name for name in archive.namelist() if is_image_page_member(name)]
    except (zipfile.BadZipFile, OSError) as exc:
        raise CbzWriteError(f"Not a valid comic archive (ZIP): {path}") from exc


def _list_image_pages_cbr(path: Path) -> list[str]:
    try:
        with open_cbr(path) as archive:
            return [
                name
                for name in iter_archive_file_members(archive)
                if is_image_page_member(name)
            ]
    except CbrReadError as exc:
        raise CbzWriteError(str(exc)) from exc


def _patch_page_count(xml_bytes: bytes, page_count: int, source_label: str) -> bytes:
    root = parse_comicinfo_root(xml_bytes, source_label)
    updated = False
    for element in root.iter():
        if local_name(element.tag).casefold() == "pagecount":
            element.text = str(page_count)
            updated = True
            break
    if not updated:
        return xml_bytes
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _is_root_member_name(name: str) -> bool:
    if not name or name.endswith(("/", "\\")):
        return False
    return "/" not in name.replace("\\", "/")


def _basename_member_name(name: str) -> str:
    return PurePosixPath(name.replace("\\", "/")).name


def _rewrite_cbz_rename(source: Path, dest: Path, renames: dict[str, str]) -> None:
    """Rewrite archive, flattening image pages to the root and dropping folder entries."""
    with zipfile.ZipFile(source, "r") as zin, zipfile.ZipFile(dest, "w") as zout:
        zout.comment = zin.comment
        comicinfo_written = False
        for item in zin.infolist():
            name = item.filename
            if name.endswith(("/", "\\")):
                continue
            if name in renames:
                zout.writestr(renames[name], zin.read(name))
                continue
            if is_image_page_member(name):
                if not _is_root_member_name(name):
                    flat = _basename_member_name(name)
                    zout.writestr(flat, zin.read(name))
                else:
                    zout.writestr(item, zin.read(name))
                continue
            if name.lower() == _COMICINFO_LOWER:
                zout.writestr(name, zin.read(name))
                comicinfo_written = True
                continue
            if _is_root_member_name(name):
                zout.writestr(item, zin.read(name))
        if not comicinfo_written:
            xml_name = comicinfo_member_name(zin.namelist())
            if xml_name and _is_root_member_name(xml_name):
                zout.writestr(xml_name, zin.read(xml_name))


def _rewrite_cbz_omit(
    source: Path,
    dest: Path,
    omit: set[str],
    remaining_image_count: int,
) -> None:
    source_label = str(source)
    with zipfile.ZipFile(source, "r") as zin, zipfile.ZipFile(dest, "w") as zout:
        zout.comment = zin.comment
        comicinfo_written = False
        for item in zin.infolist():
            name = item.filename
            if name in omit:
                continue
            if name.lower() == _COMICINFO_LOWER:
                raw = zin.read(name)
                patched = _patch_page_count(raw, remaining_image_count, source_label)
                zout.writestr(name, patched)
                comicinfo_written = True
                continue
            zout.writestr(item, zin.read(name))
        if not comicinfo_written:
            xml_name = comicinfo_member_name(zin.namelist())
            if xml_name and xml_name not in omit:
                raw = zin.read(xml_name)
                patched = _patch_page_count(raw, remaining_image_count, source_label)
                zout.writestr(xml_name, patched)


def _atomic_replace_cbz(source: Path, writer) -> Path:
    """Write via *writer(tmp_path)* then replace *source*."""
    source_mode = stat.S_IMODE(source.stat().st_mode)
    tmp_path = None
    try:
        tmp_fd, tmp_name = tempfile.mkstemp(suffix=".cbz", dir=source.parent)
        os.close(tmp_fd)
        tmp_path = Path(tmp_name)
        writer(tmp_path)
        os.chmod(tmp_path, source_mode)
        os.replace(tmp_path, source)
        tmp_path = None
        return source
    except CbzWriteError:
        if tmp_path is not None and tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise
    except Exception as exc:
        if tmp_path is not None and tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise CbzWriteError(f"Unable to update comic archive: {exc}") from exc


def _remove_from_cbz(path: Path, omit: set[str], remaining_image_count: int) -> Path:
    def write_tmp(dest: Path) -> None:
        _rewrite_cbz_omit(path, dest, omit, remaining_image_count)

    return _atomic_replace_cbz(path, write_tmp)


def _rename_in_cbz(path: Path, renames: dict[str, str]) -> Path:
    def write_tmp(dest: Path) -> None:
        _rewrite_cbz_rename(path, dest, renames)

    return _atomic_replace_cbz(path, write_tmp)


def _write_cbz_from_cbr_rename(cbr_path: Path, dest: Path, renames: dict[str, str]) -> None:
    with open_cbr(cbr_path) as archive, zipfile.ZipFile(dest, "w") as zout:
        comicinfo_written = False
        for name in iter_archive_file_members(archive):
            if name.endswith(("/", "\\")):
                continue
            if name in renames:
                zout.writestr(renames[name], archive.read(name))
                continue
            if is_image_page_member(name):
                if not _is_root_member_name(name):
                    zout.writestr(_basename_member_name(name), archive.read(name))
                else:
                    zout.writestr(name, archive.read(name))
                continue
            if name.lower() == _COMICINFO_LOWER:
                zout.writestr(COMICINFO_NAME, archive.read(name))
                comicinfo_written = True
                continue
            if _is_root_member_name(name):
                zout.writestr(name, archive.read(name))
        if not comicinfo_written:
            xml_name = comicinfo_member_name(archive.namelist())
            if xml_name and _is_root_member_name(xml_name):
                zout.writestr(COMICINFO_NAME, archive.read(xml_name))


def _rename_in_cbr(cbr_path: Path, renames: dict[str, str]) -> Path:
    if cbr_path.suffix.casefold() != ".cbr":
        raise CbzWriteError(f"Not a RAR comic archive (.cbr): {cbr_path}")
    cbz_path = cbr_path.with_suffix(".cbz")
    if cbz_path.exists():
        raise CbzWriteError(
            f"Cannot convert {cbr_path.name}: {cbz_path.name} already exists"
        )

    source_mode = stat.S_IMODE(cbr_path.stat().st_mode)
    tmp_path = None
    try:
        tmp_fd, tmp_name = tempfile.mkstemp(suffix=".cbz", dir=cbr_path.parent)
        os.close(tmp_fd)
        tmp_path = Path(tmp_name)
        _write_cbz_from_cbr_rename(cbr_path, tmp_path, renames)
        os.chmod(tmp_path, source_mode)
        os.replace(tmp_path, cbz_path)
        tmp_path = None
        cbr_path.unlink(missing_ok=True)
        return cbz_path
    except CbzWriteError:
        if tmp_path is not None and tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise
    except CbrReadError as exc:
        if tmp_path is not None and tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise CbzWriteError(str(exc)) from exc
    except Exception as exc:
        if tmp_path is not None and tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise CbzWriteError(f"Unable to convert comic archive: {exc}") from exc


def _write_cbz_from_cbr_omit(
    cbr_path: Path,
    dest: Path,
    omit: set[str],
    remaining_image_count: int,
) -> None:
    source_label = str(cbr_path)
    with open_cbr(cbr_path) as archive, zipfile.ZipFile(dest, "w") as zout:
        comicinfo_written = False
        for name in iter_archive_file_members(archive):
            if name in omit:
                continue
            if name.lower() == _COMICINFO_LOWER:
                raw = archive.read(name)
                patched = _patch_page_count(raw, remaining_image_count, source_label)
                zout.writestr(COMICINFO_NAME, patched)
                comicinfo_written = True
                continue
            zout.writestr(name, archive.read(name))
        if not comicinfo_written:
            xml_name = comicinfo_member_name(archive.namelist())
            if xml_name and xml_name not in omit:
                raw = archive.read(xml_name)
                patched = _patch_page_count(raw, remaining_image_count, source_label)
                zout.writestr(COMICINFO_NAME, patched)


def _remove_from_cbr(cbr_path: Path, omit: set[str], remaining_image_count: int) -> Path:
    if cbr_path.suffix.casefold() != ".cbr":
        raise CbzWriteError(f"Not a RAR comic archive (.cbr): {cbr_path}")
    cbz_path = cbr_path.with_suffix(".cbz")
    if cbz_path.exists():
        raise CbzWriteError(
            f"Cannot convert {cbr_path.name}: {cbz_path.name} already exists"
        )

    source_mode = stat.S_IMODE(cbr_path.stat().st_mode)
    tmp_path = None
    try:
        tmp_fd, tmp_name = tempfile.mkstemp(suffix=".cbz", dir=cbr_path.parent)
        os.close(tmp_fd)
        tmp_path = Path(tmp_name)
        _write_cbz_from_cbr_omit(cbr_path, tmp_path, omit, remaining_image_count)
        os.chmod(tmp_path, source_mode)
        os.replace(tmp_path, cbz_path)
        tmp_path = None
        cbr_path.unlink(missing_ok=True)
        return cbz_path
    except CbzWriteError:
        if tmp_path is not None and tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise
    except CbrReadError as exc:
        if tmp_path is not None and tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise CbzWriteError(str(exc)) from exc
    except Exception as exc:
        if tmp_path is not None and tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise CbzWriteError(f"Unable to convert comic archive: {exc}") from exc
