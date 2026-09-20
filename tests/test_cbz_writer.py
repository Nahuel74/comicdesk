"""Tests for safe ComicInfo persistence in CBZ archives."""

import zipfile
import xml.etree.ElementTree as ET
import stat

import pytest

from comicdesk.models import Comic
from comicdesk.services.cbz_reader import read_cbz_metadata
from comicdesk.services import cbz_writer
from comicdesk.services.cbz_writer import CbzWriteError, write_cbz_metadata


def _make_cbz(path, xml=b"<ComicInfo />", member="page.jpg"):
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("ComicInfo.xml", xml)
        archive.writestr(member, b"image")


def test_writes_and_reads_enriched_metadata(tmp_path):
    path = tmp_path / "book.cbz"
    _make_cbz(path)
    comic = Comic(path, title="A & B", series_name="Series", notes="Read this", summary="Summary",
                  publisher="Publisher", tags="hero, action", web_links=["https://one.test", "https://two.test"])

    assert write_cbz_metadata(comic) == path
    result = read_cbz_metadata(path)

    assert result.title == "A & B"
    assert result.notes == "Read this"
    assert result.summary == "Summary"
    assert result.publisher == "Publisher"
    assert result.web_links == ["https://one.test", "https://two.test"]
    assert result.tags == "hero, action"


def test_writes_comic_vine_ids_and_reads_them_back(tmp_path):
    path = tmp_path / "cv-ids.cbz"
    _make_cbz(path)
    comic = Comic(
        path,
        title="Issue",
        cv_series_id="200",
        cv_issue_id="100",
        web_links=["https://comicvine.gamespot.com/foo/4000-100/"],
    )

    write_cbz_metadata(comic)
    with zipfile.ZipFile(path) as archive:
        xml = archive.read("ComicInfo.xml").decode()

    assert "<ComicDeskCvIssueId>100</ComicDeskCvIssueId>" in xml
    assert "<ComicDeskCvSeriesId>200</ComicDeskCvSeriesId>" in xml

    result = read_cbz_metadata(path)
    assert result.cv_issue_id == "100"
    assert result.cv_series_id == "200"


def test_preserves_unknown_tags_and_namespaces(tmp_path):
    path = tmp_path / "unknown.cbz"
    xml = (b'<ComicInfo xmlns:x="urn:extra"><Title>Old</Title>'
           b'<x:Future custom="yes"><x:Value>kept</x:Value></x:Future></ComicInfo>')
    _make_cbz(path, xml)

    write_cbz_metadata(Comic(path, title="New"))
    with zipfile.ZipFile(path) as archive:
        root = ET.fromstring(archive.read("ComicInfo.xml"))

    future = next(element for element in root if element.tag.endswith("Future"))
    assert future.attrib["custom"] == "yes"
    assert future[0].text == "kept"
    assert next(element for element in root if element.tag.endswith("Title")).text == "New"


def test_corrupt_existing_xml_does_not_replace_archive(tmp_path):
    path = tmp_path / "broken.cbz"
    original = b"<ComicInfo><Title>broken"
    _make_cbz(path, original)
    before = path.read_bytes()

    with pytest.raises(CbzWriteError, match="corrupt"):
        write_cbz_metadata(Comic(path, title="Replacement"))

    assert path.read_bytes() == before


def test_invalid_existing_root_does_not_replace_archive(tmp_path):
    path = tmp_path / "wrong-root.cbz"
    _make_cbz(path, b"<NotComicInfo><Title>Original</Title></NotComicInfo>")
    before = path.read_bytes()

    with pytest.raises(CbzWriteError, match="invalid root"):
        write_cbz_metadata(Comic(path, title="Replacement"))

    assert path.read_bytes() == before


def test_replacement_preserves_source_permissions(tmp_path):
    path = tmp_path / "permissions.cbz"
    _make_cbz(path)
    path.chmod(0o640)

    write_cbz_metadata(Comic(path, title="Replacement"))

    assert stat.S_IMODE(path.stat().st_mode) == 0o640


def test_corrupt_zip_does_not_replace_file(tmp_path):
    path = tmp_path / "broken.cbz"
    path.write_bytes(b"not a zip")
    before = path.read_bytes()

    with pytest.raises(CbzWriteError):
        write_cbz_metadata(Comic(path, title="Replacement"))

    assert path.read_bytes() == before


def test_replace_failure_keeps_original_archive(tmp_path, monkeypatch):
    path = tmp_path / "replace-failure.cbz"
    _make_cbz(path, b"<ComicInfo><Title>Original</Title></ComicInfo>")
    before = path.read_bytes()

    def fail_replace(source, destination):
        raise OSError("read-only destination")

    monkeypatch.setattr(cbz_writer.os, "replace", fail_replace)
    with pytest.raises(CbzWriteError, match="Unable to write"):
        write_cbz_metadata(Comic(path, title="New"))

    assert path.read_bytes() == before
