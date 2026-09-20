"""Tests for CBZ/CBR comic archive facade and CBR conversion."""

import zipfile

import pytest

from comicdesk.models import Comic
from comicdesk.services import cbr_writer
from comicdesk.services.cbr_backend import (
    _InMemoryCbrArchive,
    reset_cbr_opener_for_tests,
    set_cbr_opener_for_tests,
)
from comicdesk.services.cbz_reader import scan_folder
from comicdesk.services.cbz_writer import CbzWriteError
from comicdesk.services.comic_archive import (
    iter_comic_files,
    read_comic_metadata,
    write_comic_metadata,
)

SAMPLE_XML = b"""<?xml version="1.0" encoding="utf-8"?>
<ComicInfo>
    <Series>Batman</Series>
    <Number>1</Number>
    <Year>2016</Year>
</ComicInfo>
"""


@pytest.fixture(autouse=True)
def _reset_cbr_backend():
    yield
    reset_cbr_opener_for_tests()


def _write_zip_cbr(path, members: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in members.items():
            archive.writestr(name, data)


def _register_fake_cbr(members: dict[str, bytes]):
    def opener(path):
        return _InMemoryCbrArchive(members)

    set_cbr_opener_for_tests(opener)


def test_iter_comic_files_finds_cbz_and_cbr(tmp_path):
    (tmp_path / "a.cbz").touch()
    (tmp_path / "b.cbr").touch()
    names = {p.name for p in iter_comic_files(tmp_path)}
    assert names == {"a.cbz", "b.cbr"}


def test_scan_folder_includes_cbr(tmp_path):
    cbz = tmp_path / "one.cbz"
    with zipfile.ZipFile(cbz, "w") as archive:
        archive.writestr("ComicInfo.xml", SAMPLE_XML)

    cbr = tmp_path / "two.cbr"
    cbr.write_bytes(b"placeholder")
    _register_fake_cbr({"ComicInfo.xml": SAMPLE_XML, "page.jpg": b"img"})

    def opener(path):
        if path.resolve() == cbr.resolve():
            return _InMemoryCbrArchive(
                {"ComicInfo.xml": SAMPLE_XML, "page.jpg": b"img"}
            )
        raise AssertionError(f"unexpected path {path}")

    set_cbr_opener_for_tests(opener)
    comics = scan_folder(tmp_path)
    assert len(comics) == 2
    by_name = {c.path.name: c for c in comics}
    assert by_name["one.cbz"].series_name == "Batman"
    assert by_name["two.cbr"].series_name == "Batman"


def test_read_cbr_without_comicinfo_uses_filename(tmp_path):
    path = tmp_path / "Saga v1 001.cbr"
    path.write_bytes(b"x")
    _register_fake_cbr({"page.jpg": b"img"})
    comic = read_comic_metadata(path)
    assert comic.series_name == "Saga"
    assert comic.issue_number == "1"


def test_cbr_conversion_skips_rar_directory_entries(tmp_path):
    """Folder-only RAR members (e.g. Zone/) must not be passed to read()."""
    cbr = tmp_path / "nested.cbr"
    cbr.write_bytes(b"rar-bytes")

    class _ArchiveWithFolder:
        def namelist(self):
            return ["Zone/", "Zone/page.jpg"]

        def read(self, name: str) -> bytes:
            if name == "Zone/page.jpg":
                return b"page"
            raise OSError(f"no data: {name}")

        def close(self):
            return None

    set_cbr_opener_for_tests(lambda _path: _ArchiveWithFolder())
    comic = Comic(path=cbr, title="Nested")
    write_comic_metadata(comic)
    with zipfile.ZipFile(cbr.with_suffix(".cbz")) as archive:
        assert archive.namelist() == ["Zone/page.jpg", "ComicInfo.xml"]


def test_cbr_conversion_writes_cbz_and_removes_cbr(tmp_path):
    cbr = tmp_path / "book.cbr"
    cbr.write_bytes(b"rar-bytes")
    _register_fake_cbr(
        {
            "ComicInfo.xml": SAMPLE_XML,
            "01.jpg": b"page-one",
            "02.jpg": b"page-two",
        }
    )
    comic = Comic(path=cbr, title="Updated title")
    result = write_comic_metadata(comic)
    cbz = tmp_path / "book.cbz"
    assert result == cbz
    assert comic.path == cbz
    assert not cbr.exists()
    with zipfile.ZipFile(cbz) as archive:
        names = archive.namelist()
        assert "ComicInfo.xml" in names
        assert "01.jpg" in names
        assert archive.read("01.jpg") == b"page-one"
        xml = archive.read("ComicInfo.xml").decode()
        assert "Updated title" in xml


def test_cbr_conversion_fails_when_cbz_exists(tmp_path):
    cbr = tmp_path / "book.cbr"
    cbr.write_bytes(b"rar")
    (tmp_path / "book.cbz").write_bytes(b"zip")
    _register_fake_cbr({"page.jpg": b"x"})
    with pytest.raises(CbzWriteError, match="already exists"):
        write_comic_metadata(Comic(path=cbr, title="T"))
    assert cbr.exists()


def test_misnamed_zip_cbr_save_writes_cbz(tmp_path):
    cbr = tmp_path / "book.cbr"
    _write_zip_cbr(
        cbr,
        {
            "ComicInfo.xml": SAMPLE_XML,
            "01.jpg": b"page-one",
            "02.jpg": b"page-two",
        },
    )
    comic = Comic(path=cbr, title="Updated title")
    result = write_comic_metadata(comic)
    cbz = tmp_path / "book.cbz"
    assert result == cbz
    assert comic.path == cbz
    assert not cbr.exists()
    with zipfile.ZipFile(cbz) as archive:
        names = archive.namelist()
        assert "ComicInfo.xml" in names
        assert "01.jpg" in names
        assert archive.read("01.jpg") == b"page-one"
        xml = archive.read("ComicInfo.xml").decode()
        assert "Updated title" in xml


def test_misnamed_zip_cbr_read_comicinfo(tmp_path):
    path = tmp_path / "book.cbr"
    _write_zip_cbr(path, {"ComicInfo.xml": SAMPLE_XML, "page.jpg": b"img"})
    comic = read_comic_metadata(path)
    assert comic.series_name == "Batman"
    assert comic.issue_number == "1"


def test_misnamed_zip_cbr_collision_when_cbz_exists(tmp_path):
    cbr = tmp_path / "book.cbr"
    _write_zip_cbr(cbr, {"page.jpg": b"x"})
    (tmp_path / "book.cbz").write_bytes(b"zip")
    with pytest.raises(CbzWriteError, match="already exists"):
        write_comic_metadata(Comic(path=cbr, title="T"))
    assert cbr.exists()


def test_invalid_cbr_save_fails_cleanly(tmp_path):
    cbr = tmp_path / "book.cbr"
    cbr.write_bytes(b"not a zip or rar archive")
    with pytest.raises(CbzWriteError):
        write_comic_metadata(Comic(path=cbr, title="T"))
    assert cbr.exists()
    assert not (tmp_path / "book.cbz").exists()


def test_cbr_conversion_replace_failure_keeps_cbr(tmp_path, monkeypatch):
    cbr = tmp_path / "book.cbr"
    cbr.write_bytes(b"rar")
    before = cbr.read_bytes()
    _register_fake_cbr({"page.jpg": b"x"})

    def fail_replace(source, destination):
        raise OSError("read-only destination")

    monkeypatch.setattr(cbr_writer.os, "replace", fail_replace)
    with pytest.raises(CbzWriteError, match="convert"):
        write_comic_metadata(Comic(path=cbr, title="T"))
    assert cbr.read_bytes() == before
    assert not (tmp_path / "book.cbz").exists()
