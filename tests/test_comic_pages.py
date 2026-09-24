"""Tests for listing and removing image pages from comic archives."""

import warnings
import zipfile
import xml.etree.ElementTree as ET

import pytest

from comicdesk.models import Comic
from comicdesk.services.cbr_backend import in_memory_cbr, set_cbr_opener_for_tests, reset_cbr_opener_for_tests
from comicdesk.services.cbz_writer import CbzWriteError
from comicdesk.services.comic_pages import (
    detect_extraneous_image_pages,
    list_image_pages,
    logical_page_number_from_member_name,
    read_image_member_bytes,
    remove_image_pages,
    rename_image_members,
)
from comicdesk.utils.page_rename_template import (
    full_rename_map_for_comic,
    plan_page_member_renames,
    plan_page_rename_apply_allowed,
)
from comicdesk.utils.rename_template import RenameRowStatus


def _make_ultimates_like_cbz(path, page_count: str = "3"):
    story = [
        "Ultimates (2015-) 003-001.jpg",
        "Ultimates (2015-) 003-002.jpg",
        "Ultimates (2015-) 003-003.jpg",
    ]
    xml = (
        f'<?xml version="1.0" encoding="utf-8"?>'
        f"<ComicInfo><PageCount>{page_count}</PageCount></ComicInfo>"
    ).encode()
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("ComicInfo.xml", xml)
        for name in story:
            archive.writestr(name, b"img")
        archive.writestr("zWater.jpg", b"water")


def test_list_image_pages_in_order(tmp_path):
    path = tmp_path / "book.cbz"
    _make_ultimates_like_cbz(path)

    assert list_image_pages(path) == [
        "Ultimates (2015-) 003-001.jpg",
        "Ultimates (2015-) 003-002.jpg",
        "Ultimates (2015-) 003-003.jpg",
        "zWater.jpg",
    ]


def test_remove_watermark_only(tmp_path):
    path = tmp_path / "copy.cbz"
    _make_ultimates_like_cbz(path)
    before_story = list_image_pages(path)

    result = remove_image_pages(path, ["zWater.jpg"])

    assert result == path
    assert list_image_pages(path) == before_story[:-1]
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        assert "zWater.jpg" not in names
        assert "ComicInfo.xml" in names
        root = ET.fromstring(archive.read("ComicInfo.xml"))
        page_count = next(
            element for element in root if element.tag.endswith("PageCount")
        )
        assert page_count.text == "3"


def test_remove_middle_pages_preserves_order(tmp_path):
    path = tmp_path / "book.cbz"
    _make_ultimates_like_cbz(path)

    remove_image_pages(path, ["Ultimates (2015-) 003-002.jpg"])

    assert list_image_pages(path) == [
        "Ultimates (2015-) 003-001.jpg",
        "Ultimates (2015-) 003-003.jpg",
        "zWater.jpg",
    ]


def test_reject_removing_all_images(tmp_path):
    path = tmp_path / "book.cbz"
    _make_ultimates_like_cbz(path)
    before = path.read_bytes()
    all_pages = list_image_pages(path)

    with pytest.raises(CbzWriteError, match="At least one image"):
        remove_image_pages(path, all_pages)

    assert path.read_bytes() == before


def test_reject_empty_selection(tmp_path):
    path = tmp_path / "book.cbz"
    _make_ultimates_like_cbz(path)
    before = path.read_bytes()

    with pytest.raises(CbzWriteError, match="No pages selected"):
        remove_image_pages(path, [])

    assert path.read_bytes() == before


def test_missing_archive_raises(tmp_path):
    path = tmp_path / "missing.cbz"

    with pytest.raises(CbzWriteError, match="not found"):
        list_image_pages(path)


def test_remove_cbr_converts_to_cbz(tmp_path):
    members = {
        "ComicInfo.xml": b"<ComicInfo><PageCount>2</PageCount></ComicInfo>",
        "a.jpg": b"a",
        "b.jpg": b"b",
        "extra.jpg": b"x",
    }
    cbr_path = tmp_path / "book.cbr"

    def opener(_path):
        return in_memory_cbr(members).__enter__()

    set_cbr_opener_for_tests(lambda path: in_memory_cbr(members).__enter__())
    try:
        cbr_path.write_bytes(b"placeholder")
        remove_image_pages(cbr_path, ["extra.jpg"])
    finally:
        reset_cbr_opener_for_tests()

    cbz_path = tmp_path / "book.cbz"
    assert cbz_path.is_file()
    assert not cbr_path.exists()
    assert list_image_pages(cbz_path) == ["a.jpg", "b.jpg"]


def test_logical_page_number_from_scan_filename():
    assert logical_page_number_from_member_name("Ultimates (2015-) 001-003.jpg") == 3
    assert logical_page_number_from_member_name("Ultimates (2015-) 003-001.jpg") == 1
    assert logical_page_number_from_member_name("Page 12.png") == 12
    assert logical_page_number_from_member_name("cover.jpg") is None


@pytest.mark.parametrize(
    ("pages", "expected"),
    [
        (
            [
                "Ultimates (2015-) 003-001.jpg",
                "Ultimates (2015-) 003-002.jpg",
                "Ultimates (2015-) 003-003.jpg",
                "zWater.jpg",
            ],
            ["zWater.jpg"],
        ),
        (["001.jpg", "002.jpg", "003.jpg"], []),
        (["Page 01.jpg", "Page 02.jpg"], []),
        (["001.jpg", "002.jpg", "random.jpg"], ["random.jpg"]),
        (["001.jpg", "frontcover.jpg", "002.jpg"], []),
        (["001.jpg", "002.jpg", "credits.jpg"], ["credits.jpg"]),
        (["story-01.png", "story-02.png", "zCredit.jpg"], ["zCredit.jpg"]),
    ],
)
def test_detect_extraneous_image_pages(pages, expected):
    assert detect_extraneous_image_pages(pages) == expected


def test_read_image_member_bytes(tmp_path):
    path = tmp_path / "book.cbz"
    payload = b"\xff\xd8\xff fake jpeg"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("ComicInfo.xml", b"<ComicInfo />")
        archive.writestr("page.jpg", payload)

    assert read_image_member_bytes(path, "page.jpg") == payload

    with pytest.raises(CbzWriteError, match="Not an image"):
        read_image_member_bytes(path, "ComicInfo.xml")


def test_rename_image_members_preserves_order(tmp_path):
    path = tmp_path / "book.cbz"
    _make_ultimates_like_cbz(path)
    rename_image_members(
        path,
        {"Ultimates (2015-) 003-001.jpg": "renamed-001.jpg"},
    )
    assert list_image_pages(path) == [
        "renamed-001.jpg",
        "Ultimates (2015-) 003-002.jpg",
        "Ultimates (2015-) 003-003.jpg",
        "zWater.jpg",
    ]


def test_rename_rejects_duplicate_targets(tmp_path):
    path = tmp_path / "book.cbz"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("ComicInfo.xml", b"<ComicInfo />")
        archive.writestr("a.jpg", b"a")
        archive.writestr("b.jpg", b"b")

    with pytest.raises(CbzWriteError, match="Duplicate"):
        rename_image_members(path, {"a.jpg": "same.jpg", "b.jpg": "same.jpg"})


def test_rename_keeps_page_count(tmp_path):
    path = tmp_path / "book.cbz"
    xml = b'<?xml version="1.0"?><ComicInfo><PageCount>2</PageCount></ComicInfo>'
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("ComicInfo.xml", xml)
        archive.writestr("a.jpg", b"a")
        archive.writestr("b.jpg", b"b")
    rename_image_members(path, {"a.jpg": "new-a.jpg"})
    with zipfile.ZipFile(path, "r") as archive:
        info = archive.read("ComicInfo.xml").decode()
    assert "<PageCount>2</PageCount>" in info


def test_rename_flattens_nested_folders(tmp_path):
    path = tmp_path / "book.cbz"
    nested = "release group/page.jpg"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("ComicInfo.xml", b"<ComicInfo />")
        archive.writestr(nested, b"img")
        archive.writestr("release group/", b"")
    rename_image_members(path, {nested: "Avengers - 019 - 001.jpg"})
    with zipfile.ZipFile(path, "r") as archive:
        names = archive.namelist()
    assert names == ["ComicInfo.xml", "Avengers - 019 - 001.jpg"]
    assert list_image_pages(path) == ["Avengers - 019 - 001.jpg"]


def _archive_member_bytes(path) -> dict[str, bytes]:
    with zipfile.ZipFile(path, "r") as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def test_ultimates_partial_scan_rename_preserves_bytes(tmp_path):
    path = tmp_path / "Ultimates 001 (2016) (Digital) (Zone-Empire).cbz"
    xml = (
        b"<?xml version='1.0'?><ComicInfo>"
        b"<Series>Ultimates</Series><Number>1</Number>"
        b"</ComicInfo>"
    )
    payloads = {
        "Ultimates (2015-) 001-003.jpg": b"PAGE3",
        "Ultimates (2015-) 001-004.jpg": b"PAGE4",
    }
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("ComicInfo.xml", xml)
        for name, data in payloads.items():
            archive.writestr(name, data)

    comic = Comic(path)
    rows = plan_page_member_renames([comic], "{Series} - {Number} - {Page}")
    mapping = full_rename_map_for_comic(rows, comic)
    rename_image_members(path, mapping)

    assert list_image_pages(path) == [
        "Ultimates - 1 - 3.jpg",
        "Ultimates - 1 - 4.jpg",
    ]
    assert read_image_member_bytes(path, "Ultimates - 1 - 3.jpg") == b"PAGE3"
    assert read_image_member_bytes(path, "Ultimates - 1 - 4.jpg") == b"PAGE4"
    with zipfile.ZipFile(path, "r") as archive:
        names = archive.namelist()
    assert "Ultimates - 1 - 1.jpg" not in names
    assert "Ultimates - 1 - 2.jpg" not in names


def test_plan_index_fallback_collides_with_parsed_page(tmp_path):
    path = tmp_path / "book.cbz"
    xml = (
        b"<?xml version='1.0'?><ComicInfo>"
        b"<Series>X</Series><Number>1</Number>"
        b"</ComicInfo>"
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("ComicInfo.xml", xml)
        archive.writestr("cover.jpg", b"COVER")
        archive.writestr("Ultimates (2015-) 001-001.jpg", b"PAGE1")

    comic = Comic(path)
    rows = plan_page_member_renames([comic], "{Series} - {Number} - {Page}")
    assert plan_page_rename_apply_allowed(rows)
    by_old = {row.old_name: row for row in rows}
    assert by_old["cover.jpg"].status == RenameRowStatus.EXCLUDED
    assert by_old["Ultimates (2015-) 001-001.jpg"].status == RenameRowStatus.OK

    mapping = full_rename_map_for_comic(rows, comic)
    rename_image_members(path, mapping)
    assert read_image_member_bytes(path, "X - 1 - 1.jpg") == b"PAGE1"
    assert "cover.jpg" in list_image_pages(path)


def test_ultimates_template_bulk_rename_preserves_bytes(tmp_path):
    path = tmp_path / "Ultimates 001 (2016) (Digital) (Zone-Empire).cbz"
    xml = (
        b"<?xml version='1.0'?><ComicInfo>"
        b"<Series>Ultimates</Series><Number>1</Number><PageCount>5</PageCount>"
        b"</ComicInfo>"
    )
    payloads = {
        "Ultimates (2015-) 001-001.jpg": b"PAGE1",
        "Ultimates (2015-) 001-002.jpg": b"PAGE2",
        "Ultimates (2015-) 001-003.jpg": b"PAGE3",
        "Ultimates (2015-) 001-004.jpg": b"PAGE4",
        "zWater.jpg": b"WATER",
    }
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("ComicInfo.xml", xml)
        for name, data in payloads.items():
            archive.writestr(name, data)

    comic = Comic(path)
    rows = plan_page_member_renames([comic], "{Series} - {Number} - {Page}")
    mapping = full_rename_map_for_comic(rows, comic)
    expected_order = [f"Ultimates - 1 - {index}.jpg" for index in range(1, 6)]

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        rename_image_members(path, mapping)
    assert not [w for w in caught if "Duplicate name" in str(w.message)]

    assert list_image_pages(path) == expected_order
    for index, member in enumerate(expected_order, start=1):
        assert read_image_member_bytes(path, member) == payloads[
            list(payloads.keys())[index - 1]
        ]


def test_rename_rejects_flatten_collision_with_target(tmp_path):
    path = tmp_path / "book.cbz"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("ComicInfo.xml", b"<ComicInfo />")
        archive.writestr("scan-003.jpg", b"PAGE3")
        archive.writestr("folder/Ultimates - 1 - 1.jpg", b"HIDDEN")

    before = _archive_member_bytes(path)
    with pytest.raises(CbzWriteError, match="Duplicate archive path"):
        rename_image_members(path, {"scan-003.jpg": "Ultimates - 1 - 1.jpg"})
    assert _archive_member_bytes(path) == before


def test_rename_rejects_twin_nested_flatten_collision(tmp_path):
    path = tmp_path / "book.cbz"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("ComicInfo.xml", b"<ComicInfo />")
        archive.writestr("a/p.jpg", b"AAA")
        archive.writestr("b/p.jpg", b"BBB")
        archive.writestr("cover.jpg", b"COVER")

    before = _archive_member_bytes(path)
    with pytest.raises(CbzWriteError, match="Duplicate archive path"):
        rename_image_members(path, {"cover.jpg": "Cover-1.jpg"})
    assert _archive_member_bytes(path) == before
