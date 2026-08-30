"""Offscreen smoke tests for the CBZ metadata panel."""

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from cbl_maker.models import Comic, ComicVineIssue, ComicVineVolume
from cbl_maker.ui.cbz_metadata_panel import CbzMetadataPanel


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


def test_panel_populates_supported_fields_without_mutating_comic(qapp):
    comic = Comic(Path("book.cbz"), title="Title", series_name="Series", notes="Notes")
    panel = CbzMetadataPanel(comic)

    assert panel.inputs["title"].text() == "Title"
    assert panel.inputs["series_name"].text() == "Series"
    assert panel.inputs["notes"].toPlainText() == "Notes"
    panel.inputs["title"].setText("Draft title")
    assert comic.title == "Title"
    assert panel.session.is_dirty
    panel.shutdown_workers()


def test_ambiguous_candidates_require_explicit_selection(qapp):
    comic = Comic(Path("book.cbz"))
    panel = CbzMetadataPanel(comic)
    first = ComicVineIssue("1", "2", "Series", "1", "1", "2020", "url")
    second = ComicVineIssue("2", "2", "Series", "1", "2", "2020", "url")

    panel._show_candidates([first, second])
    assert panel.apply_button.isEnabled() is False
    panel.candidates_list.setCurrentRow(1)
    assert panel.apply_button.isEnabled() is True
    assert comic.cv_issue_id is None
    panel.shutdown_workers()


def test_panel_selector_switches_between_available_comics(qapp):
    first = Comic(Path("one.cbz"), title="One")
    second = Comic(Path("two.cbz"), title="Two")
    panel = CbzMetadataPanel(first)
    panel.set_comics([first, second])

    assert panel.comic_selector.count() == 2
    panel.comic_selector.setCurrentIndex(1)

    assert panel.comic is second
    assert panel.session.draft.title == "Two"
    panel.shutdown_workers()


def test_volume_candidate_can_be_applied_to_draft(qapp):
    comic = Comic(Path("book.cbz"), issue_number="3")
    panel = CbzMetadataPanel(comic)
    volume = ComicVineVolume("42", "Saga", "2012", "url", count_of_issues="66")
    panel._show_candidates([volume])
    panel.candidates_list.setCurrentRow(0)
    panel.apply_proposal()

    assert panel.session.draft.cv_series_id == "42"
    assert panel.session.draft.volume == "2012"
    assert panel.session.draft.count == "66"
    assert comic.cv_series_id is None
    panel.shutdown_workers()
