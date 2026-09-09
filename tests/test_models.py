"""Regression tests for application data models."""

from pathlib import Path

from comicdesk.models import Comic, ComicVineMetadata


def test_new_comic_has_no_comicvine_metadata():
    comic = Comic(path=Path("/comic.cbz"))

    assert comic.cv_metadata is None


def test_comicvine_metadata_is_kept_alongside_legacy_ids_and_manual_fields():
    metadata = ComicVineMetadata(
        id="139720",
        series_id="23227",
        series_name="Comic Vine Series",
        volume="2",
        issue_number="7",
        cover_date="2020-01-01",
        web_url="https://comicvine.gamespot.com/issue/4000-139720/",
    )
    comic = Comic(
        path=Path("/comic.cbz"),
        series_name="Manual Series",
        issue_number="manual-7",
        cv_series_id="manual-series-id",
        cv_issue_id="manual-issue-id",
        cv_metadata=metadata,
    )

    assert comic.cv_metadata is metadata
    assert comic.cv_series_id == "manual-series-id"
    assert comic.cv_issue_id == "manual-issue-id"
    assert comic.series_name == "Manual Series"
    assert comic.issue_number == "manual-7"
    assert comic.has_cv_ids is True


def test_empty_comicvine_ids_are_not_present():
    comic = Comic(path=Path("/comic.cbz"), cv_series_id="", cv_issue_id="")

    assert comic.has_cv_ids is False
    assert comic.status == "❌"


def test_partial_comicvine_ids_are_incomplete():
    comic = Comic(path=Path("/comic.cbz"), cv_series_id="123", cv_issue_id="")

    assert comic.has_cv_ids is False
    assert comic.status == "⚠️"
