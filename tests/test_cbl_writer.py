"""Tests for CBL writer module."""

import pytest
from pathlib import Path

from comicdesk.models import ComicVineIssue, ReadingList, Comic
from comicdesk.services.cbl_reader import read_cbl
from comicdesk.services.cbl_writer import generate_cbl, save_cbl


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

    def test_includes_order_configuration(self, sample_comics):
        reading_list = ReadingList(
            name="Ordered List",
            comics=sample_comics,
            ordered_by="series_issue",
            order_direction="desc",
        )

        xml = generate_cbl(reading_list)

        assert 'orderedby="series_issue"' in xml
        assert 'orderdirection="desc"' in xml

    def test_order_configuration_round_trips_through_reader(self, sample_comics):
        reading_list = ReadingList(
            name="Ordered List",
            comics=sample_comics,
            ordered_by="volume",
            order_direction="desc",
        )

        document = read_cbl(generate_cbl(reading_list))

        assert document.ordered_by == "volume"
        assert document.order_direction == "desc"

    def test_preserves_database_and_comicvine_metadata(self):
        metadata = ComicVineIssue(
            "20", "10", "Saga", "1", "2", "2020-01-01", "https://example.test/20"
        )
        comic = Comic(
            path=Path("/local/secret/saga.cbz"),
            series_name="Saga",
            volume="1",
            issue_number="2",
            cv_series_id="10",
            cv_issue_id="20",
            cv_metadata=metadata,
        )

        document = read_cbl(generate_cbl(ReadingList("Saga", [comic])))

        assert document.books[0].cv_series_id == "10"
        assert document.books[0].cv_issue_id == "20"
        assert document.books[0].cv_metadata == metadata

    def test_writes_comicdesk_namespace(self):
        metadata = ComicVineIssue("20", "10", "Saga", "1", "2", "2020-01-01", "url")
        comic = Comic(
            path=Path("/local/saga.cbz"),
            cv_series_id="10",
            cv_issue_id="20",
            cv_metadata=metadata,
        )

        xml = generate_cbl(ReadingList("Saga", [comic]))

        assert "https://comicdesk.dev/xml/metadata" in xml
        assert "https://cbl-maker.dev/xml/metadata" not in xml


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
