"""Tests for series gap analysis."""

from pathlib import Path

from comicdesk.models import Comic
from comicdesk.services.series_gaps import (
    all_missing_issues_as_cbl_books,
    analyze_series_gaps,
    missing_issues_as_cbl_books,
)


def test_analyze_series_gaps_detects_missing_numbers():
    comics = [
        Comic(
            Path("a.cbz"),
            series_name="Test",
            issue_number="1",
            count="3",
            cv_series_id="4050-1",
        ),
        Comic(
            Path("b.cbz"),
            series_name="Test",
            issue_number="3",
            count="3",
            cv_series_id="4050-1",
        ),
    ]
    reports = analyze_series_gaps(comics)
    assert len(reports) == 1
    assert reports[0].missing_numbers == [2.0]
    books = missing_issues_as_cbl_books(reports[0])
    assert len(books) == 1
    assert books[0].issue_number == "2"


def test_all_missing_issues_as_cbl_books_skips_complete_series():
    comics = [
        Comic(Path("a.cbz"), series_name="A", issue_number="1", count="1"),
        Comic(Path("b.cbz"), series_name="B", issue_number="1", count="2"),
        Comic(Path("c.cbz"), series_name="B", issue_number="3", count="2"),
    ]
    reports = analyze_series_gaps(comics)
    books = all_missing_issues_as_cbl_books(reports)
    assert len(books) == 1
    assert books[0].series_name == "B"
    assert books[0].issue_number == "2"
