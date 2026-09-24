"""Tests for listing and removing image pages from comic archives."""

import zipfile
import xml.etree.ElementTree as ET

import pytest

from comicdesk.services.cbr_backend import in_memory_cbr, set_cbr_opener_for_tests, reset_cbr_opener_for_tests
from comicdesk.services.cbz_writer import CbzWriteError
from comicdesk.services.comic_pages import (
    detect_extraneous_image_pages,
    list_image_pages,
    read_image_member_bytes,
    remove_image_pages,
    rename_image_members,
)


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

    with pytest.raises(CbzWriteError, match="Duplicate target"):
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
