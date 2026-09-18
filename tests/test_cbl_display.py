"""Tests for CBL display and enrichment helpers."""

from comicdesk.models import CBLBook, Comic, ComicVineIssue
from comicdesk.services.cbl_display import (
    cbl_book_issue_label,
    cbl_book_series_label,
    comic_release_display,
    enrich_cbl_book,
)


def test_enrich_cbl_book_fills_series_from_metadata():
    meta = ComicVineIssue(
        "1", "10", "Batman", "2018", "7", "2018-01-01", "url",
    )
    book = CBLBook(cv_issue_id="1", cv_metadata=meta)
    enriched = enrich_cbl_book(book)
    assert enriched.series_name == "Batman"
    assert enriched.issue_number == "7"


def test_cbl_book_series_label_falls_back_to_metadata():
    meta = ComicVineIssue("1", "10", "Saga", "", "12", "", "url")
    book = CBLBook(cv_metadata=meta)
    assert cbl_book_series_label(book) == "Saga"
    assert cbl_book_issue_label(book) == "12"


def test_comic_release_display_prefers_comicinfo_date():
    comic = Comic(path="x.cbz", year="2013", month="7", day="4")
    assert comic_release_display(comic) == "2013-07-04"


def test_comic_release_display_year_only_from_cbl():
    comic = Comic(path="", series_name="X", year="2005")
    assert comic_release_display(comic) == "2005-01-01"
