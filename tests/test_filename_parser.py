"""Offline tests for comic archive filename parsing."""

from pathlib import Path

from comicdesk.utils.filename_parser import ParsedFilename, parse_comic_filename


def test_parses_series_issue_volume_and_year_from_common_filename():
    parsed = parse_comic_filename(Path("The Amazing Spider-Man Vol. 02 #003 (2018).cbz"))

    assert parsed == ParsedFilename(
        series_name="The Amazing Spider Man", issue_number="3", volume="2", year="2018"
    )


def test_parses_hashless_issue_and_short_volume_markers():
    parsed = parse_comic_filename("Saga v1 001.cbz")

    assert parsed.series_name == "Saga"
    assert parsed.volume == "1"
    assert parsed.issue_number == "1"
    assert parsed.year == ""


def test_removes_trailing_release_tags_before_parsing_issue():
    parsed = parse_comic_filename("Batman 007 [Digital] [CBZ].cbz")

    assert parsed.series_name == "Batman"
    assert parsed.issue_number == "7"


def test_dots_underscores_and_hyphens_are_normalized_as_separators():
    parsed = parse_comic_filename("X-Men_Annual.010.cbz")

    assert parsed.series_name == "X Men Annual"
    assert parsed.issue_number == "10"


def test_year_is_not_treated_as_issue_number():
    parsed = parse_comic_filename("Series (2024).cbz")

    assert parsed.series_name == "Series"
    assert parsed.issue_number == ""
    assert parsed.year == "2024"


def test_accepts_stem_without_archive_suffix():
    parsed = parse_comic_filename("Series - #0004")

    assert parsed.series_name == "Series"
    assert parsed.issue_number == "4"


def test_strips_parenthetical_release_tags_after_publication_year():
    parsed = parse_comic_filename(
        "Excalibur 001 (2004) (Digital) (Shadowcat-Empire).cbz"
    )

    assert parsed == ParsedFilename(
        series_name="Excalibur", issue_number="1", volume="", year="2004"
    )


def test_empty_and_missing_paths_return_empty_metadata():
    assert parse_comic_filename(None) == ParsedFilename()
    assert parse_comic_filename("") == ParsedFilename()
