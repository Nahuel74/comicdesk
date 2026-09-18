"""Offscreen smoke tests for the CBZ metadata panel."""

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from comicdesk.models import Comic, ComicVineIssue, ComicVineVolume
from comicdesk.ui.cbz_metadata_panel import CbzMetadataPanel, CHANGED_PROPERTY


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


def test_update_button_removed(qapp):
    """The Update button must no longer exist in the panel."""
    comic = Comic(Path("book.cbz"))
    panel = CbzMetadataPanel(comic)

    assert not hasattr(panel, "refresh_button")
    assert not hasattr(panel, "update_button")
    panel.shutdown_workers()


def test_apply_overwrites_existing_fields(qapp):
    """Apply must overwrite preexisting metadata when a proposal is applied."""
    comic = Comic(
        Path("book.cbz"),
        series_name="Old Series",
        issue_number="1",
        volume="1",
        year="2000",
    )
    panel = CbzMetadataPanel(comic)
    proposal = ComicVineIssue(
        id="100", series_id="200", series_name="New Series",
        volume="2015", issue_number="5", cover_date="2015-06-01",
        web_url="https://comicvine.test/4000-100/",
        name="New Title",
    )

    panel._show_candidates([proposal])
    panel.candidates_list.setCurrentRow(0)
    panel.apply_proposal()

    draft = panel.session.draft
    assert draft.series_name == "New Series"
    assert draft.issue_number == "5"
    assert draft.volume == "2015"
    assert draft.title == "New Title"
    assert draft.cv_issue_id == "100"
    assert draft.cv_series_id == "200"
    panel.shutdown_workers()


def test_apply_highlights_changed_fields(qapp):
    """Fields that changed after apply must receive the metadataChanged property."""
    comic = Comic(
        Path("book.cbz"),
        series_name="Old Series",
        issue_number="1",
        volume="1",
    )
    panel = CbzMetadataPanel(comic)
    proposal = ComicVineIssue(
        id="100", series_id="200", series_name="New Series",
        volume="2015", issue_number="5", cover_date="2015-06-01",
        web_url="https://comicvine.test/4000-100/",
    )

    panel._show_candidates([proposal])
    panel.candidates_list.setCurrentRow(0)
    panel.apply_proposal()

    assert panel.inputs["series_name"].property(CHANGED_PROPERTY) is True
    assert panel.inputs["issue_number"].property(CHANGED_PROPERTY) is True
    assert panel.inputs["volume"].property(CHANGED_PROPERTY) is True
    panel.shutdown_workers()


def test_apply_does_not_highlight_unchanged_fields(qapp):
    """Fields that did not change must not receive the changed highlight."""
    comic = Comic(
        Path("book.cbz"),
        series_name="Same Series",
        issue_number="1",
    )
    panel = CbzMetadataPanel(comic)
    proposal = ComicVineIssue(
        id="100", series_id="200", series_name="Same Series",
        volume="2015", issue_number="1", cover_date="2015-06-01",
        web_url="https://comicvine.test/4000-100/",
    )

    panel._show_candidates([proposal])
    panel.candidates_list.setCurrentRow(0)
    panel.apply_proposal()

    assert panel.inputs["series_name"].property(CHANGED_PROPERTY) is False
    assert panel.inputs["issue_number"].property(CHANGED_PROPERTY) is False
    assert panel.inputs["volume"].property(CHANGED_PROPERTY) is True
    panel.shutdown_workers()


def test_discard_clears_changed_highlights(qapp):
    """Discarding the draft must clear all changed-field highlights."""
    comic = Comic(Path("book.cbz"), series_name="Old", volume="1")
    panel = CbzMetadataPanel(comic)
    proposal = ComicVineIssue(
        id="100", series_id="200", series_name="New",
        volume="2015", issue_number="5", cover_date="2015-06-01",
        web_url="https://comicvine.test/4000-100/",
    )

    panel._show_candidates([proposal])
    panel.candidates_list.setCurrentRow(0)
    panel.apply_proposal()
    assert panel.inputs["series_name"].property(CHANGED_PROPERTY) is True

    panel.discard()
    assert panel.inputs["series_name"].property(CHANGED_PROPERTY) is False
    panel.shutdown_workers()


def test_changing_comic_clears_changed_highlights(qapp):
    """Switching to a different comic must clear all changed-field highlights."""
    first = Comic(Path("one.cbz"), series_name="One", volume="1")
    second = Comic(Path("two.cbz"), series_name="Two", volume="2")
    panel = CbzMetadataPanel(first)

    proposal = ComicVineIssue(
        id="100", series_id="200", series_name="Changed",
        volume="2015", issue_number="5", cover_date="2015-06-01",
        web_url="https://comicvine.test/4000-100/",
    )
    panel._show_candidates([proposal])
    panel.candidates_list.setCurrentRow(0)
    panel.apply_proposal()
    assert panel.inputs["series_name"].property(CHANGED_PROPERTY) is True

    panel.discard()
    panel.set_comic(second)
    assert panel.inputs["series_name"].property(CHANGED_PROPERTY) is False
    panel.shutdown_workers()


def test_stop_hydrate_worker_releases_previous_worker(qapp, monkeypatch):
    panel = CbzMetadataPanel(Comic(Path("book.cbz")))
    released = []
    monkeypatch.setattr(panel, "_release_worker", lambda worker: released.append(worker))
    sentinel = object()
    panel._hydrate_worker = sentinel

    panel._stop_hydrate_worker()

    assert released == [sentinel]
    assert panel._hydrate_worker is None
    panel.shutdown_workers()


def test_stale_hydrate_finished_releases_worker(qapp, monkeypatch):
    panel = CbzMetadataPanel(Comic(Path("book.cbz")))
    released = []
    monkeypatch.setattr(panel, "_release_worker", lambda worker: released.append(worker))
    worker = object()

    panel._hydrate_finished(None, worker, panel._request_token, panel._path_key)

    assert released == [worker]
    panel.shutdown_workers()
