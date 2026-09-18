"""Convert CBR to CBZ with updated ComicInfo.xml atomically."""

from __future__ import annotations

import os
import stat
import tempfile
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

from comicdesk.models import Comic
from comicdesk.services.cbr_backend import (
    CbrReadError,
    COMICINFO_NAME,
    comicinfo_member_name,
    iter_archive_file_members,
    open_cbr,
)
from comicdesk.services.cbz_writer import (
    CbzWriteError,
    comicinfo_xml_bytes,
    parse_comicinfo_root,
)

_COMICINFO_LOWER = COMICINFO_NAME.lower()


def write_cbr_as_cbz_metadata(comic: Comic) -> Path:
    """Create a CBZ next to the CBR with metadata, then remove the CBR on success."""
    cbr_path = Path(comic.path)
    if not cbr_path.is_file():
        raise CbzWriteError(f"Comic archive not found: {cbr_path}")
    if cbr_path.suffix.lower() != ".cbr":
        raise CbzWriteError(f"Not a RAR comic archive (.cbr): {cbr_path}")

    cbz_path = cbr_path.with_suffix(".cbz")
    if cbz_path.exists():
        raise CbzWriteError(
            f"Cannot convert {cbr_path.name}: {cbz_path.name} already exists"
        )

    source_mode = None
    tmp_path = None
    try:
        source_mode = stat.S_IMODE(cbr_path.stat().st_mode)
        xml_bytes = _build_comicinfo_xml_from_cbr(cbr_path, comic)
        tmp_fd, tmp_name = tempfile.mkstemp(suffix=".cbz", dir=cbr_path.parent)
        os.close(tmp_fd)
        tmp_path = Path(tmp_name)
        _write_cbz_from_cbr(cbr_path, tmp_path, xml_bytes)
        _validate_cbz(tmp_path)
        os.chmod(tmp_path, source_mode)
        os.replace(tmp_path, cbz_path)
        tmp_path = None
        cbr_path.unlink(missing_ok=True)
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

    comic.path = cbz_path
    return cbz_path


def _build_comicinfo_xml_from_cbr(cbr_path: Path, comic: Comic) -> bytes:
    root = ET.Element("ComicInfo")
    with open_cbr(cbr_path) as archive:
        xml_name = comicinfo_member_name(archive.namelist())
        if xml_name:
            root = parse_comicinfo_root(archive.read(xml_name), str(cbr_path))
    return comicinfo_xml_bytes(comic, root)


def _write_cbz_from_cbr(cbr_path: Path, dest: Path, xml_bytes: bytes) -> None:
    with open_cbr(cbr_path) as archive, zipfile.ZipFile(dest, "w") as zout:
        for name in iter_archive_file_members(archive):
            if name.lower() == _COMICINFO_LOWER:
                continue
            zout.writestr(name, archive.read(name))
        zout.writestr(COMICINFO_NAME, xml_bytes)


def _validate_cbz(path: Path) -> None:
    if path.stat().st_size <= 0:
        raise CbzWriteError(f"Converted archive is empty: {path}")
    try:
        with zipfile.ZipFile(path, "r") as archive:
            xml_name = comicinfo_member_name(archive.namelist())
            if not xml_name:
                raise CbzWriteError(f"Converted archive has no ComicInfo.xml: {path}")
            parse_comicinfo_root(archive.read(xml_name), str(path))
    except zipfile.BadZipFile as exc:
        raise CbzWriteError(f"Converted archive is not a valid ZIP: {path}") from exc
