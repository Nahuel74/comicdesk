"""Tests for archive page member rename templates."""

import zipfile

from comicdesk.models import Comic
from comicdesk.services.metadata_session import MetadataSession
from comicdesk.utils.page_rename_template import (
    comic_metadata_for_page_template,
    plan_page_member_renames,
    plan_page_rename_apply_allowed,
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


def test_plan_scan_page_zero_not_renumbered_to_index(tmp_path):
    path = tmp_path / "book.cbz"
    xml = (
        b"<?xml version='1.0'?><ComicInfo>"
        b"<Series>Ultimates</Series><Number>1</Number>"
        b"</ComicInfo>"
    )
    members = [
        "Ultimates (2015-) 001-000.jpg",
        "Ultimates (2015-) 001-001.jpg",
    ]
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("ComicInfo.xml", xml)
        for name in members:
            archive.writestr(name, b"x")
    comic = Comic(path)
    rows = plan_page_member_renames([comic], "{Series} - {Number} - {Page}")
    by_old = {row.old_name: row for row in rows}
    assert by_old["Ultimates (2015-) 001-000.jpg"].proposed_name == (
        "Ultimates - 1 - 0.jpg"
    )
    assert by_old["Ultimates (2015-) 001-000.jpg"].status == RenameRowStatus.OK
    assert by_old["Ultimates (2015-) 001-001.jpg"].proposed_name == (
        "Ultimates - 1 - 1.jpg"
    )
    assert plan_page_rename_apply_allowed(rows)


def test_plan_ultimates_partial_scan_keeps_page_segment(tmp_path):
    path = tmp_path / "Ultimates 001 (2016) (Digital) (Zone-Empire).cbz"
    xml = (
        b"<?xml version='1.0'?><ComicInfo>"
        b"<Series>Ultimates</Series><Number>1</Number>"
        b"</ComicInfo>"
    )
    members = [
        "Ultimates (2015-) 001-003.jpg",
        "Ultimates (2015-) 001-004.jpg",
    ]
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("ComicInfo.xml", xml)
        for name in members:
            archive.writestr(name, b"x")
    comic = Comic(path)
    rows = plan_page_member_renames([comic], "{Series} - {Number} - {Page}")
    by_old = {row.old_name: row for row in rows}
    assert by_old["Ultimates (2015-) 001-003.jpg"].proposed_name == (
        "Ultimates - 1 - 3.jpg"
    )
    assert by_old["Ultimates (2015-) 001-004.jpg"].proposed_name == (
        "Ultimates - 1 - 4.jpg"
    )


def test_page_does_not_inherit_issue_count_padding(tmp_path):
    path = tmp_path / "book.cbz"
    xml = (
        b"<?xml version='1.0'?><ComicInfo>"
        b"<Series>Ultimates</Series><Number>1</Number><Count>12</Count>"
        b"</ComicInfo>"
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("ComicInfo.xml", xml)
        archive.writestr("Ultimates (2015-) 001-003.jpg", b"x")
    comic = Comic(path)
    rows = plan_page_member_renames([comic], "{Series} - {Number} - {Page}")
    assert rows[0].proposed_name == "Ultimates - 001 - 3.jpg"


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
    assert statuses["a.jpg"] == RenameRowStatus.OK
    assert statuses["b.jpg"] == RenameRowStatus.EXCLUDED
    assert plan_page_rename_apply_allowed(rows)


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


def test_plan_resolves_duplicate_scan_page_target(tmp_path):
    path = tmp_path / "Ultimates 001 (2016).cbz"
    xml = (
        b"<?xml version='1.0'?><ComicInfo>"
        b"<Series>Ultimates</Series><Number>1</Number>"
        b"</ComicInfo>"
    )
    members = [f"Ultimates (2015-) 001-{i:03d}.jpg" for i in range(1, 18)]
    members.append("Ultimates 001 (2016) (Digital)/Ultimates (2015-) 001-017.jpg")
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("ComicInfo.xml", xml)
        for name in members:
            archive.writestr(name, b"x")
    comic = Comic(path)
    rows = plan_page_member_renames([comic], "{Series} - {Number} - {Page}")
    by_old = {row.old_name: row for row in rows}
    assert by_old["Ultimates (2015-) 001-017.jpg"].status == RenameRowStatus.OK
    assert by_old["Ultimates (2015-) 001-017.jpg"].proposed_name == (
        "Ultimates - 1 - 17.jpg"
    )
    nested = "Ultimates 001 (2016) (Digital)/Ultimates (2015-) 001-017.jpg"
    assert by_old[nested].status == RenameRowStatus.EXCLUDED
    assert plan_page_rename_apply_allowed(rows)


def test_plan_detects_output_path_collision_with_unchanged_root(tmp_path):
    path = tmp_path / "book.cbz"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "ComicInfo.xml",
            b"<ComicInfo><Series>X</Series><Number>1</Number></ComicInfo>",
        )
        archive.writestr("target.jpg", b"keep")
        archive.writestr("rename-me.jpg", b"move")
    comic = Comic(path)
    rows = plan_page_member_renames([comic], "target")
    assert not plan_page_rename_apply_allowed(rows)
    by_old = {row.old_name: row for row in rows}
    assert by_old["rename-me.jpg"].status == RenameRowStatus.COLLISION
    assert by_old["target.jpg"].status == RenameRowStatus.COLLISION
