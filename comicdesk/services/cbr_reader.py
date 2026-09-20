"""Read metadata from CBR archives."""

from __future__ import annotations

from pathlib import Path

from comicdesk.models import Comic
from comicdesk.services.cbr_backend import CbrReadError, comicinfo_member_name, open_cbr
from comicdesk.services.cbz_reader import read_cbz_metadata
from comicdesk.services.cbz_writer import is_zip_comic_archive
from comicdesk.services.comicinfo import parse_comicinfo
from comicdesk.utils.filename_parser import parse_comic_filename


def read_cbr_metadata(cbr_path: Path) -> Comic:
    """Read ComicInfo from a CBR when possible; always returns a Comic for the path."""
    cbr_path = Path(cbr_path)
    if is_zip_comic_archive(cbr_path):
        return _apply_filename_heuristics(read_cbz_metadata(cbr_path))

    comic = Comic(path=cbr_path)

    try:
        with open_cbr(cbr_path) as archive:
            xml_name = comicinfo_member_name(archive.namelist())
            if xml_name:
                comic = parse_comicinfo(archive.read(xml_name), cbr_path)
    except CbrReadError:
        pass

    return _apply_filename_heuristics(comic)


def _apply_filename_heuristics(comic: Comic) -> Comic:
    """Fill series/issue/year from the filename when ComicInfo did not provide them."""
    if comic.series_name and comic.issue_number and comic.year:
        return comic
    parsed = parse_comic_filename(comic.path)
    if not comic.series_name and parsed.series_name:
        comic.series_name = parsed.series_name
    if not comic.issue_number and parsed.issue_number:
        comic.issue_number = parsed.issue_number
    if not comic.volume and parsed.volume:
        comic.volume = parsed.volume
    if not comic.year and parsed.year:
        comic.year = parsed.year
    return comic
