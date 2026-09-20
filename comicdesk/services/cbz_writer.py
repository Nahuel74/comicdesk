"""Write ComicInfo.xml into a CBZ archive atomically."""

from __future__ import annotations

import os
import stat
import tempfile
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

from comicdesk.models import Comic
from comicdesk.services.comicinfo import comic_to_element, local_name

COMICINFO_NAME = "ComicInfo.xml"


class CbzWriteError(Exception):
    """Raised when a CBZ cannot be updated safely."""


def write_cbz_metadata(comic: Comic) -> Path:
    """Persist comic metadata into ComicInfo.xml without corrupting the archive."""
    cbz_path = Path(comic.path)
    if not cbz_path.is_file():
        raise CbzWriteError(f"Comic archive not found: {cbz_path}")

    source_mode = None
    tmp_path = None
    try:
        source_mode = stat.S_IMODE(cbz_path.stat().st_mode)
        xml_bytes = _build_comicinfo_xml(cbz_path, comic)
        tmp_fd, tmp_name = tempfile.mkstemp(suffix=".cbz", dir=cbz_path.parent)
        os.close(tmp_fd)
        tmp_path = Path(tmp_name)
        _rewrite_archive(cbz_path, tmp_path, xml_bytes)
        os.chmod(tmp_path, source_mode)
        os.replace(tmp_path, cbz_path)
    except CbzWriteError:
        if tmp_path is not None and tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise
    except Exception as exc:
        if tmp_path is not None and tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise CbzWriteError(f"Unable to write comic metadata: {exc}") from exc
    return cbz_path


def is_zip_comic_archive(path: Path) -> bool:
    """True when *path* is a readable ZIP archive (e.g. misnamed .cbr CBZ)."""
    path = Path(path)
    if not path.is_file():
        return False
    try:
        with zipfile.ZipFile(path, "r") as archive:
            archive.namelist()
        return True
    except (zipfile.BadZipFile, OSError):
        return False


def comicinfo_xml_bytes(comic: Comic, root: ET.Element | None = None) -> bytes:
    """Serialize ComicInfo.xml bytes, merging *comic* into an optional existing root."""
    if root is None:
        root = ET.Element("ComicInfo")
    root = comic_to_element(comic, root)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def parse_comicinfo_root(raw: bytes, source_label: str) -> ET.Element:
    """Parse ComicInfo bytes or raise CbzWriteError."""
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise CbzWriteError(f"ComicInfo.xml is corrupt: {source_label}") from exc
    if local_name(root.tag).casefold() != "comicinfo":
        raise CbzWriteError(f"ComicInfo.xml has an invalid root: {source_label}")
    return root


def _build_comicinfo_xml(cbz_path: Path, comic: Comic) -> bytes:
    root = _load_existing_root(cbz_path)
    return comicinfo_xml_bytes(comic, root)


def _load_existing_root(cbz_path: Path) -> ET.Element:
    try:
        with zipfile.ZipFile(cbz_path, "r") as archive:
            xml_name = _comicinfo_member(archive)
            if not xml_name:
                return ET.Element("ComicInfo")
            raw = archive.read(xml_name)
    except (zipfile.BadZipFile, OSError, KeyError) as exc:
        raise CbzWriteError(f"Not a valid comic archive (ZIP): {cbz_path}") from exc

    return parse_comicinfo_root(raw, str(cbz_path))


def _rewrite_archive(source: Path, dest: Path, xml_bytes: bytes) -> None:
    with zipfile.ZipFile(source, "r") as zin, zipfile.ZipFile(dest, "w") as zout:
        zout.comment = zin.comment
        for item in zin.infolist():
            if item.filename.lower() == COMICINFO_NAME.lower():
                continue
            zout.writestr(item, zin.read(item.filename))
        zout.writestr(COMICINFO_NAME, xml_bytes)


def _comicinfo_member(archive: zipfile.ZipFile) -> str | None:
    for name in archive.namelist():
        if name.lower() == COMICINFO_NAME.lower():
            return name
    return None
