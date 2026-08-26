"""Tests for CBZ reader module."""

import zipfile
import tempfile
from pathlib import Path
import pytest

from cbl_maker.services.cbz_reader import read_cbz_metadata, scan_folder


SAMPLE_XML = """<?xml version="1.0" encoding="utf-8"?>
<ComicInfo>
    <Series>Batman</Series>
    <Volume>2016</Volume>
    <Number>1</Number>
    <Year>2016</Year>
    <Web>https://comicvine.gamespot.com/batman/4050-12345/</Web>
    <Notes>Test notes</Notes>
</ComicInfo>
"""


@pytest.fixture
def sample_cbz(tmp_path):
    """Create a sample CBZ file for testing."""
    cbz_path = tmp_path / "test.cbz"
    with zipfile.ZipFile(cbz_path, "w") as zf:
        zf.writestr("ComicInfo.xml", SAMPLE_XML)
        zf.writestr("page1.jpg", b"fake image data")
    return cbz_path


@pytest.fixture
def empty_cbz(tmp_path):
    """Create a CBZ file without ComicInfo.xml."""
    cbz_path = tmp_path / "empty.cbz"
    with zipfile.ZipFile(cbz_path, "w") as zf:
        zf.writestr("page1.jpg", b"fake image data")
    return cbz_path


class TestReadCbzMetadata:
    """Tests for read_cbz_metadata function."""

    def test_reads_series_name(self, sample_cbz):
        comic = read_cbz_metadata(sample_cbz)
        assert comic.series_name == "Batman"

    def test_reads_volume(self, sample_cbz):
        comic = read_cbz_metadata(sample_cbz)
        assert comic.volume == "2016"

    def test_reads_issue_number(self, sample_cbz):
        comic = read_cbz_metadata(sample_cbz)
        assert comic.issue_number == "1"

    def test_reads_year(self, sample_cbz):
        comic = read_cbz_metadata(sample_cbz)
        assert comic.year == "2016"

    def test_extracts_cv_series_id(self, sample_cbz):
        comic = read_cbz_metadata(sample_cbz)
        assert comic.cv_series_id == "12345"

    def test_handles_missing_xml(self, empty_cbz):
        comic = read_cbz_metadata(empty_cbz)
        assert comic.series_name == ""
        assert comic.cv_series_id is None

    def test_handles_invalid_file(self, tmp_path):
        invalid = tmp_path / "invalid.cbz"
        invalid.write_bytes(b"not a zip file")
        comic = read_cbz_metadata(invalid)
        assert comic.series_name == ""


class TestScanFolder:
    """Tests for scan_folder function."""

    def test_finds_cbz_files(self, tmp_path, sample_cbz):
        comics = scan_folder(tmp_path)
        assert len(comics) == 1
        assert comics[0].series_name == "Batman"

    def test_recursive_scan(self, tmp_path, sample_cbz):
        subfolder = tmp_path / "sub"
        subfolder.mkdir()
        sub_cbz = subfolder / "sub.cbz"
        with zipfile.ZipFile(sub_cbz, "w") as zf:
            zf.writestr("ComicInfo.xml", SAMPLE_XML)

        comics = scan_folder(tmp_path, recursive=True)
        assert len(comics) == 2

    def test_non_recursive_scan(self, tmp_path, sample_cbz):
        subfolder = tmp_path / "sub"
        subfolder.mkdir()
        sub_cbz = subfolder / "sub.cbz"
        with zipfile.ZipFile(sub_cbz, "w") as zf:
            zf.writestr("ComicInfo.xml", SAMPLE_XML)

        comics = scan_folder(tmp_path, recursive=False)
        assert len(comics) == 1
