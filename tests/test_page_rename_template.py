"""Tests for archive page member rename templates."""

import zipfile

from comicdesk.models import Comic
from comicdesk.services.metadata_session import MetadataSession
from comicdesk.utils.page_rename_template import (
    comic_metadata_for_page_template,
    plan_page_member_renames,
    proposed_member_name,
)
from comicdesk.utils.rename_template import RenameRowStatus


def _make_cbz(path, names: list[str], *, series: str = "", number: str = "") -> None:
    parts = ["<ComicInfo><PageCount>2</PageCount>"]
    if series:
        parts.append(f"<Series>{series}</Series>")
    if number:
        parts.append(f"<Number>{number}</Number>")
    parts.append("</ComicInfo>")
    xml = "".join(parts).encode()
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("ComicInfo.xml", xml)
        for name in names:
            archive.writestr(name, b"x")


def test_page_padding_in_template(tmp_path):
    path = tmp_path / "book.cbz"
    _make_cbz(path, ["old.jpg"], series="Alpha", number="3")
    comic = Comic(path)
    meta = comic_metadata_for_page_template(comic)
    name = proposed_member_name(
        "{Series}-{Page}",
        meta,
        "old.jpg",
        1,
        1,
        page_pad_width=3,
    )
    assert name == "Alpha-001.jpg"


def test_plan_detects_intra_archive_collision(tmp_path):
    path = tmp_path / "book.cbz"
    _make_cbz(path, ["a.jpg", "b.jpg"], series="Same", number="1")
    comic = Comic(path)
    rows = plan_page_member_renames(
        [comic],
        "{Series}.jpg",
        page_pad_width=0,
    )
    statuses = {row.old_name: row.status for row in rows}
    assert statuses["a.jpg"] == RenameRowStatus.COLLISION
    assert statuses["b.jpg"] == RenameRowStatus.COLLISION


def test_plan_uses_comicinfo_series_not_library_stale(tmp_path):
    path = tmp_path / "book.cbz"
    xml = (
        b"<?xml version='1.0'?><ComicInfo>"
        b"<Series>The Avengers (2024)</Series><Number>19</Number>"
        b"</ComicInfo>"
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("ComicInfo.xml", xml)
        archive.writestr("001.jpg", b"x")
    library_comic = Comic(path, series_name="Avengers", issue_number="019")
    rows = plan_page_member_renames(
        [library_comic],
        "{Series} - {Number} - {Page}",
        page_pad_width=3,
    )
    assert rows[0].status == RenameRowStatus.OK
    assert rows[0].proposed_name == "The Avengers (2024) - 19 - 001.jpg"


def test_metadata_session_override_wins_over_comicinfo(tmp_path):
    path = tmp_path / "book.cbz"
    _make_cbz(path, ["001.jpg"], series="Short", number="1")
    library = Comic(path, series_name="Short", issue_number="1")
    session = MetadataSession(library)
    session.set_field("series_name", "Avengers 019 (2024) (Digital) (Shan-Empire)")
    session.set_field("issue_number", "019")
    rows = plan_page_member_renames(
        [library],
        "{Series} - {Number} - {Page}",
        page_pad_width=3,
        metadata_for=lambda _comic: session.snapshot(),
    )
    assert rows[0].proposed_name == (
        "Avengers 019 (2024) (Digital) (Shan-Empire) - 019 - 001.jpg"
    )

def test_plan_ok_renames(tmp_path):
    path = tmp_path / "book.cbz"
    _make_cbz(path, ["001.jpg", "002.jpg"], series="Beta", number="2")
    comic = Comic(path)
    rows = plan_page_member_renames(
        [comic],
        "{Series} - {Number} - {Page}",
        page_pad_width=2,
    )
    by_old = {row.old_name: row for row in rows}
    assert by_old["001.jpg"].status == RenameRowStatus.OK
    assert by_old["001.jpg"].proposed_name == "Beta - 2 - 01.jpg"


def test_page_folder_placeholder(tmp_path):
    path = tmp_path / "book.cbz"
    member = "Avengers 019 (2024) (Digital) (Shan-Empire)/page.jpg"
    _make_cbz(path, [member], series="Avengers", number="19")
    comic = Comic(path)
    name = proposed_member_name(
        "{PageFolder} {Page:5}",
        comic_metadata_for_page_template(comic),
        member,
        1,
        1,
    )
    assert name == "Avengers 019 (2024) (Digital) (Shan-Empire) 00001.jpg"
