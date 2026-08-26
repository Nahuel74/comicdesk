"""Tests for CBL writer module."""

import pytest
from pathlib import Path

from cbl_maker.models import ReadingList, Comic
from cbl_maker.services.cbl_writer import generate_cbl, save_cbl


@pytest.fixture
def sample_comics():
    """Create sample comics for testing."""
    comic1 = Comic(
        path=Path("/test/comic1.cbz"),
        series_name="Doctor Strange and Dr. Doom Triumph and Torment",
        volume="1989",
        issue_number="1",
        year="1989",
        cv_series_id="23227",
        cv_issue_id="139720"
    )
    comic2 = Comic(
        path=Path("/test/comic2.cbz"),
        series_name="Avengers",
        volume="2023",
        issue_number="19",
        year="2023",
        cv_series_id="150431",
        cv_issue_id="1074674"
    )
    return [comic1, comic2]


@pytest.fixture
def sample_list(sample_comics):
    """Create a sample reading list."""
    return ReadingList(
        name="One World Under Doom (2025)",
        comics=sample_comics
    )


class TestGenerateCbl:
    """Tests for generate_cbl function."""

    def test_generates_valid_xml(self, sample_list):
        xml = generate_cbl(sample_list)
        assert '<?xml version="1.0"' in xml
        assert "<ReadingList" in xml

    def test_includes_list_name(self, sample_list):
        xml = generate_cbl(sample_list)
        assert "<Name>One World Under Doom (2025)</Name>" in xml

    def test_includes_book_attributes(self, sample_list):
        xml = generate_cbl(sample_list)
        assert 'SeriesName="Doctor Strange and Dr. Doom Triumph and Torment"' in xml
        assert 'Volume="1989"' in xml
        assert 'Issue="1"' in xml

    def test_includes_database_element(self, sample_list):
        xml = generate_cbl(sample_list)
        assert '<Database Name="cv" Series="23227" Issue="139720"' in xml

    def test_comic_without_cv_ids(self):
        comic = Comic(
            path=Path("/test.cbz"),
            series_name="Test",
            volume="2024",
            issue_number="1"
        )
        reading_list = ReadingList(name="Test List", comics=[comic])
        xml = generate_cbl(reading_list)
        assert "<Book" in xml
        # Should not have Database element
        assert "<Database" not in xml or comic.cv_series_id is None

    def test_does_not_write_incomplete_database_for_empty_cv_id(self):
        comic = Comic(
            path=Path("/test.cbz"),
            series_name="Test",
            cv_series_id="",
            cv_issue_id="123",
        )
        xml = generate_cbl(ReadingList(name="Test List", comics=[comic]))

        assert "<Database" not in xml


class TestSaveCbl:
    """Tests for save_cbl function."""

    def test_saves_file(self, tmp_path, sample_list):
        xml = generate_cbl(sample_list)
        output = tmp_path / "test.cbl"
        save_cbl(xml, output)
        assert output.exists()

    def test_creates_parent_dirs(self, tmp_path, sample_list):
        xml = generate_cbl(sample_list)
        output = tmp_path / "sub" / "dir" / "test.cbl"
        save_cbl(xml, output)
        assert output.exists()

    def test_file_content_matches(self, tmp_path, sample_list):
        xml = generate_cbl(sample_list)
        output = tmp_path / "test.cbl"
        save_cbl(xml, output)
        content = output.read_text(encoding="utf-8")
        assert xml == content
