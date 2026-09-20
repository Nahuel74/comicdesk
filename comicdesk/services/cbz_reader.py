"""CBZ file reader - extracts metadata from ComicInfo.xml."""

import zipfile
from pathlib import Path

from comicdesk.models import Comic
from comicdesk.services.comicinfo import parse_comicinfo

_COMICINFO_BASENAME = "comicinfo.xml"


def _comicinfo_member_name(zf: zipfile.ZipFile) -> str | None:
    try:
        zf.getinfo("ComicInfo.xml")
        return "ComicInfo.xml"
    except KeyError:
        pass
    for info in zf.infolist():
        if info.filename.lower() == _COMICINFO_BASENAME:
            return info.filename
    return None


def read_cbz_metadata(cbz_path: Path) -> Comic:
    """
    Read metadata from a CBZ file.

    Args:
        cbz_path: Path to the CBZ file

    Returns:
        Comic object with extracted metadata
    """
    comic = Comic(path=cbz_path)

    try:
        with zipfile.ZipFile(cbz_path, "r") as zf:
            xml_name = _comicinfo_member_name(zf)
            if not xml_name:
                return comic

            comic = parse_comicinfo(zf.read(xml_name), cbz_path)

    except (zipfile.BadZipFile, OSError, ValueError):
        pass

    return comic


def scan_folder(folder_path: Path, recursive: bool = True) -> list[Comic]:
    """
    Scan a folder for CBZ/CBR files and read their metadata.

    Args:
        folder_path: Path to scan
        recursive: If True, scan subfolders

    Returns:
        List of Comic objects
    """
    from comicdesk.services.comic_archive import scan_comics

    return scan_comics(folder_path, recursive)
