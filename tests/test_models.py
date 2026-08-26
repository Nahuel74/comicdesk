"""Regression tests for application data models."""

from pathlib import Path

from cbl_maker.models import Comic


def test_empty_comicvine_ids_are_not_present():
    comic = Comic(path=Path("/comic.cbz"), cv_series_id="", cv_issue_id="")

    assert comic.has_cv_ids is False
    assert comic.status == "❌"


def test_partial_comicvine_ids_are_incomplete():
    comic = Comic(path=Path("/comic.cbz"), cv_series_id="123", cv_issue_id="")

    assert comic.has_cv_ids is False
    assert comic.status == "⚠️"
