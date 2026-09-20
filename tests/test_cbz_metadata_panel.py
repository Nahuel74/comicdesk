"""Offscreen smoke tests for the CBZ metadata panel."""

import os
import threading
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QItemSelectionModel, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox, QTableView, QWidget

from comicdesk.models import Comic, ComicVineIssue, ComicVineVolume
from comicdesk.ui.cbz_metadata_panel import CbzMetadataPanel, CHANGED_PROPERTY
from comicdesk.ui.comicvine_candidate_widgets import CoverLoader


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


def test_show_candidates_uses_rich_row_widgets(qapp):
    comic = Comic(Path("book.cbz"))
    panel = CbzMetadataPanel(comic)
    hit = ComicVineIssue(
        "104054", "20570", "Fantastic Four: House of M", "2005", "1", "2020", "url",
        name="A Doctor in the House",
    )
    panel._show_candidates([hit])
    assert panel.candidates_list.count() == 1
    assert panel.candidates_list.itemWidget(panel.candidates_list.item(0)) is not None
    assert "1 result" in panel.proposals_label.text()
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


def test_instance_table_uses_extended_selection(qapp):
    panel = CbzMetadataPanel(Comic(Path("book.cbz")))
    assert panel.instance_table.selectionMode() == QTableView.SelectionMode.ExtendedSelection
    panel.shutdown_workers()


def test_search_disabled_with_multiple_selection(qapp):
    first = Comic(Path("one.cbz"))
    second = Comic(Path("two.cbz"))
    panel = CbzMetadataPanel(first)
    panel.set_comics([first, second])
    sm = panel.instance_table.selectionModel()
    sm.select(
        panel.instance_model.index(0, 0),
        QItemSelectionModel.SelectionFlag.ClearAndSelect
        | QItemSelectionModel.SelectionFlag.Rows,
    )
    sm.select(
        panel.instance_model.index(1, 0),
        QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows,
    )
    assert len(panel._selected_comics()) == 2
    assert panel.search_button.isEnabled() is False
    panel.shutdown_workers()


def test_batch_apply_updates_selected_drafts(qapp, monkeypatch, tmp_path):
    comics = [
        Comic(tmp_path / "one.cbz", series_name="A"),
        Comic(tmp_path / "two.cbz", series_name="B"),
        Comic(tmp_path / "three.cbz", series_name="C"),
    ]
    for comic in comics:
        comic.path.write_bytes(b"")
    panel = CbzMetadataPanel(comics[0])
    panel.set_comics(comics)
    panel.batch_inputs["cv_series_id"].setText("100")
    panel.batch_inputs["series_name"].setText("Batch Series")
    panel.batch_inputs["volume"].setText("2010")
    sm = panel.instance_table.selectionModel()
    for row in range(3):
        flags = QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows
        if row == 0:
            flags |= QItemSelectionModel.SelectionFlag.ClearAndSelect
        sm.select(panel.instance_model.index(row, 0), flags)
    save_started: list[int] = []

    def capture_start(self):
        save_started.append(len(self._write_queue))
        return False

    monkeypatch.setattr(CbzMetadataPanel, "_start_next_write", capture_start)
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )
    panel.apply_batch_to_selected()
    assert save_started == [3]
    for comic in comics:
        session = panel._session_for_comic(comic)
        assert session.draft.cv_series_id == "100"
        assert session.draft.series_name == "Batch Series"
        assert session.draft.volume == "2010"
    panel.shutdown_workers()


def test_batch_apply_disabled_for_single_selection(qapp):
    comic = Comic(Path("one.cbz"))
    panel = CbzMetadataPanel(comic)
    panel.set_comics([comic])
    panel.batch_inputs["cv_series_id"].setText("100")
    assert panel.apply_to_selected_button.isEnabled() is False
    panel.shutdown_workers()


def test_single_selection_shows_per_issue_editor(qapp):
    comic = Comic(Path("one.cbz"))
    panel = CbzMetadataPanel(comic)
    assert panel.editor_stack.currentWidget() is panel.single_editor_page
    panel.shutdown_workers()


def test_batch_apply_skipped_when_no_field_changes(qapp, monkeypatch):
    first = Comic(Path("one.cbz"), series_name="Same", cv_series_id="1")
    second = Comic(Path("two.cbz"), series_name="Same", cv_series_id="1")
    panel = CbzMetadataPanel(first)
    panel.set_comics([first, second])
    panel.batch_inputs["cv_series_id"].setText("1")
    panel.batch_inputs["series_name"].setText("Same")
    sm = panel.instance_table.selectionModel()
    sm.select(
        panel.instance_model.index(0, 0),
        QItemSelectionModel.SelectionFlag.ClearAndSelect
        | QItemSelectionModel.SelectionFlag.Rows,
    )
    sm.select(
        panel.instance_model.index(1, 0),
        QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows,
    )
    save_started: list[int] = []
    monkeypatch.setattr(
        CbzMetadataPanel,
        "_start_next_write",
        lambda self: save_started.append(len(self._write_queue)) or False,
    )
    panel.apply_batch_to_selected()
    assert save_started == []
    panel.shutdown_workers()


def test_multi_select_disables_per_issue_form(qapp):
    first = Comic(Path("one.cbz"))
    second = Comic(Path("two.cbz"))
    panel = CbzMetadataPanel(first)
    panel.set_comics([first, second])
    sm = panel.instance_table.selectionModel()
    sm.select(
        panel.instance_model.index(0, 0),
        QItemSelectionModel.SelectionFlag.ClearAndSelect
        | QItemSelectionModel.SelectionFlag.Rows,
    )
    sm.select(
        panel.instance_model.index(1, 0),
        QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows,
    )
    assert panel.inputs["title"].isEnabled() is False
    assert panel.batch_inputs["cv_series_id"].isEnabled() is True
    assert panel.editor_stack.currentWidget() is panel.batch_editor_page
    panel.show()
    assert panel.cv_panel.isHidden() is True
    panel.shutdown_workers()


def test_single_selection_shows_comicvine_panel(qapp):
    first = Comic(Path("one.cbz"))
    second = Comic(Path("two.cbz"))
    panel = CbzMetadataPanel(first)
    panel.set_comics([first, second])
    panel.show()
    assert panel.cv_panel.isHidden() is False
    panel.shutdown_workers()


def test_working_set_context_shows_selection_and_editing(qapp):
    first = Comic(Path("alpha.cbz"), title="Alpha")
    second = Comic(Path("beta.cbz"), title="Beta")
    panel = CbzMetadataPanel(first)
    panel.set_comics([first, second])
    sm = panel.instance_table.selectionModel()
    sm.select(
        panel.instance_model.index(0, 0),
        QItemSelectionModel.SelectionFlag.ClearAndSelect
        | QItemSelectionModel.SelectionFlag.Rows,
    )
    sm.select(
        panel.instance_model.index(1, 0),
        QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows,
    )
    text = panel.working_set_context_label.text()
    assert "2 files selected" in text
    assert "Editing: alpha.cbz" in text
    assert "Comic Vine search: one file only" in text
    panel.shutdown_workers()


def test_batch_selection_list_shows_selected_files(qapp):
    first = Comic(Path("alpha.cbz"), series_name="Alpha", issue_number="1")
    second = Comic(Path("beta.cbz"), series_name="Beta", issue_number="2")
    panel = CbzMetadataPanel(first)
    panel.set_comics([first, second])
    sm = panel.instance_table.selectionModel()
    sm.select(
        panel.instance_model.index(0, 0),
        QItemSelectionModel.SelectionFlag.ClearAndSelect
        | QItemSelectionModel.SelectionFlag.Rows,
    )
    sm.select(
        panel.instance_model.index(1, 0),
        QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows,
    )
    assert panel.batch_selection_list.count() == 2
    assert "alpha.cbz" in panel.batch_selection_list.item(0).text()
    assert "Selected files (2)" in panel.batch_files_group.title()
    panel.shutdown_workers()


def test_editing_row_marker_in_table(qapp):
    comic = Comic(Path("marked.cbz"))
    panel = CbzMetadataPanel(comic)
    panel.set_comics([comic])
    index = panel.instance_model.index(0, 0)
    assert panel.instance_model.data(index) == "▸ marked.cbz"
    panel.shutdown_workers()


def test_filtered_table_row_switches_active_comic(qapp):
    first = Comic(Path("alpha.cbz"), title="Alpha")
    second = Comic(Path("beta.cbz"), title="Beta")
    panel = CbzMetadataPanel(first)
    panel.set_comics([first, second])
    panel.instance_filter.setText("beta")
    row = panel.instance_model.row_for_comic(second)
    panel.instance_table.selectionModel().setCurrentIndex(
        panel.instance_model.index(row, 0),
        QItemSelectionModel.SelectionFlag.ClearAndSelect
        | QItemSelectionModel.SelectionFlag.Rows,
    )
    assert panel.comic is second
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


def test_action_button_labels_include_step_numbers(qapp):
    first = Comic(Path("one.cbz"))
    second = Comic(Path("two.cbz"))
    panel = CbzMetadataPanel(first)
    panel.set_comics([first, second])

    assert panel.discard_button.text().startswith("3.")
    assert panel.save_button.text() == "4. Save to archive"

    panel.inputs["title"].setText("Draft one")
    key2 = panel._comic_path_key(second)
    session2 = panel._session_for_comic(second)
    session2.set_field("title", "Draft two")
    panel._extra_sessions[key2] = session2
    panel._emit_dirty()

    assert panel.save_button.text() == "4. Save 2 archives"
    panel.shutdown_workers()


def test_digit_shortcut_search_when_enabled(qapp, monkeypatch):
    comic = Comic(Path("book.cbz"))
    panel = CbzMetadataPanel(comic)
    panel.set_comics([comic])
    panel.show()
    calls: list[str] = []

    monkeypatch.setattr(panel, "_start_search", lambda: calls.append("search"))
    panel.setFocus()
    qapp.processEvents()

    QTest.keyClick(panel, Qt.Key.Key_1)
    qapp.processEvents()
    QTest.keyClick(
        panel,
        Qt.Key.Key_1,
        Qt.KeyboardModifier.KeypadModifier,
    )
    qapp.processEvents()
    assert calls == ["search", "search"]

    calls.clear()
    sm = panel.instance_table.selectionModel()
    second = Comic(Path("two.cbz"))
    panel.set_comics([comic, second])
    sm.select(
        panel.instance_model.index(0, 0),
        QItemSelectionModel.SelectionFlag.ClearAndSelect
        | QItemSelectionModel.SelectionFlag.Rows,
    )
    sm.select(
        panel.instance_model.index(1, 0),
        QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows,
    )
    assert panel.search_button.isEnabled() is False
    QTest.keyClick(panel, Qt.Key.Key_1)
    qapp.processEvents()
    assert calls == []
    panel.shutdown_workers()


def test_digit_shortcut_blocked_in_text_field(qapp, monkeypatch):
    comic = Comic(Path("book.cbz"))
    panel = CbzMetadataPanel(comic)
    panel.show()
    calls: list[str] = []
    monkeypatch.setattr(panel, "_start_search", lambda: calls.append("search"))

    panel.instance_filter.setFocus()
    qapp.processEvents()
    QTest.keyClick(panel.instance_filter, Qt.Key.Key_1)
    qapp.processEvents()
    assert calls == []
    panel.shutdown_workers()


def test_digit_shortcuts_apply_discard_save(qapp, monkeypatch):
    comic = Comic(Path("book.cbz"), series_name="Old")
    panel = CbzMetadataPanel(comic)
    panel.show()
    proposal = ComicVineIssue(
        id="100",
        series_id="200",
        series_name="New",
        volume="2015",
        issue_number="5",
        cover_date="2015-06-01",
        web_url="https://comicvine.test/4000-100/",
    )
    panel._show_candidates([proposal])
    panel.candidates_list.setCurrentRow(0)
    panel.setFocus()
    qapp.processEvents()
    assert panel.apply_button.isEnabled() is True
    QTest.keyClick(panel, Qt.Key.Key_2)
    qapp.processEvents()
    assert panel.session.draft.series_name == "New"

    panel.inputs["title"].setText("Draft")
    assert panel.discard_button.isEnabled() is True
    assert panel.save_button.isEnabled() is True

    QTest.keyClick(panel, Qt.Key.Key_3)
    qapp.processEvents()
    assert panel.session.is_dirty is False

    panel.inputs["title"].setText("Draft again")
    save_started: list[int] = []

    def capture_start(self):
        save_started.append(1)
        return False

    monkeypatch.setattr(CbzMetadataPanel, "_start_next_write", capture_start)
    QTest.keyClick(panel, Qt.Key.Key_4)
    qapp.processEvents()
    assert save_started == [1]

    panel.discard_button.setEnabled(False)
    panel.save_button.setEnabled(False)
    save_started.clear()
    QTest.keyClick(panel, Qt.Key.Key_3)
    QTest.keyClick(panel, Qt.Key.Key_4)
    qapp.processEvents()
    assert save_started == []
    panel.shutdown_workers()


def test_digit_shortcut_blocked_with_modal(qapp, monkeypatch):
    comic = Comic(Path("book.cbz"))
    panel = CbzMetadataPanel(comic)
    panel.show()
    calls: list[str] = []
    monkeypatch.setattr(panel, "_start_search", lambda: calls.append("search"))
    monkeypatch.setattr(QApplication, "activeModalWidget", lambda: QWidget())

    panel.setFocus()
    qapp.processEvents()
    QTest.keyClick(panel, Qt.Key.Key_1)
    qapp.processEvents()
    assert calls == []
    panel.shutdown_workers()


def test_stop_cover_loaders_uses_join_or_defer_delete(qapp, monkeypatch):
    panel = CbzMetadataPanel(Comic(Path("book.cbz")))
    loader = CoverLoader("https://example.test/cover.jpg", 0)
    panel._cover_loaders = [loader]
    join_calls: list[tuple] = []

    def capture_join(thread, *, defer_signals=None):
        join_calls.append((thread, defer_signals))

    monkeypatch.setattr(panel, "_join_or_defer_delete", capture_join)
    panel._stop_cover_loaders()

    assert join_calls == [(loader, (loader.finished, loader.error))]
    assert panel._cover_loaders == []
    panel.shutdown_workers()


def test_join_or_defer_delete_defers_delete_when_still_running(qapp, monkeypatch):
    panel = CbzMetadataPanel(Comic(Path("book.cbz")))
    loader = CoverLoader("https://example.test/cover.jpg", 0)
    delete_calls: list[bool] = []

    monkeypatch.setattr(loader, "deleteLater", lambda: delete_calls.append(True))
    monkeypatch.setattr(loader, "isRunning", lambda: True)
    monkeypatch.setattr(loader, "wait", lambda _ms: False)

    panel._join_or_defer_delete(loader, defer_signals=(loader.finished, loader.error))

    assert delete_calls == []
    loader.error.emit(0)
    qapp.processEvents()
    panel.shutdown_workers()


def test_shutdown_workers_with_slow_cover_loader(qapp, monkeypatch):
    import comicdesk.ui.comicvine_candidate_widgets as candidate_widgets

    blocked = threading.Event()

    def slow_get(*_args, **_kwargs):
        blocked.wait(timeout=5)
        raise RuntimeError("blocked cover fetch released")

    monkeypatch.setattr(candidate_widgets.httpx, "get", slow_get)

    panel = CbzMetadataPanel(Comic(Path("book.cbz")))
    hit = ComicVineIssue(
        "1",
        "2",
        "Series",
        "1",
        "1",
        "2020",
        "url",
        image_url="https://example.test/cover.jpg",
    )
    panel._show_candidates([hit])
    assert len(panel._cover_loaders) == 1
    loader = panel._cover_loaders[0]

    panel.shutdown_workers()
    assert panel._cover_loaders == []

    blocked.set()
    assert loader.wait(5000)
    qapp.processEvents()
    panel.shutdown_workers()
