"""Focused tests for reading-list identity and list-level actions."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QModelIndex
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from comicdesk.config import Config
from comicdesk.models import Comic
from comicdesk.models import CBLBook
from comicdesk.services.cbl_reader import CBLDocument, CBLParseError, ReconciliationResult
from comicdesk.services.wishlist import WishlistManager
from comicdesk.ui.main_window import MainWindow
from comicdesk.ui.reading_list_panel import ReadingListPanel


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def panel(qapp):
    widget = ReadingListPanel()
    yield widget
    widget.close()


def _stub_import(
    monkeypatch,
    document,
    result,
    answer=QMessageBox.StandardButton.Yes,
    wishlist_answer=QMessageBox.StandardButton.Yes,
    path="import.cbl",
):
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args: (path, ""))
    monkeypatch.setattr("comicdesk.ui.reading_list_panel.read_cbl", lambda _path: document)
    monkeypatch.setattr(
        "comicdesk.ui.reading_list_panel.reconcile_cbl",
        lambda _document, _comics: result,
    )

    def question(_parent, title, *_rest):
        if title == "Add to Wishlist":
            return wishlist_answer
        return answer

    monkeypatch.setattr(QMessageBox, "question", question)
    monkeypatch.setattr(QMessageBox, "information", lambda *args: None)


def _book_for_comic(comic: Comic) -> CBLBook:
    return CBLBook(
        series_name=comic.series_name,
        volume=comic.volume,
        issue_number=comic.issue_number,
        cv_series_id=comic.cv_series_id,
        cv_issue_id=comic.cv_issue_id,
    )


def test_valid_rename_updates_model_and_cancel_restores(panel):
    panel.name_label.setText("Weekly Picks")
    assert panel.header.commit_name() is True
    assert panel.reading_list.name == "Weekly Picks"

    panel.name_label.setText("Discarded")
    panel.header.cancel_name_edit()
    assert panel.name_label.text() == "Weekly Picks"
    assert panel.reading_list.name == "Weekly Picks"


def test_empty_name_is_rejected(panel):
    panel.name_label.setText("   ")
    assert panel.header.commit_name() is False
    assert panel.reading_list.name == "New Reading List"
    assert panel.name_label.text() == "New Reading List"


def test_actions_follow_empty_and_non_empty_states(panel):
    assert not panel.clear_btn.isEnabled()
    assert not panel.save_btn.isEnabled()
    assert not panel.export_btn.isEnabled()

    panel.add_comic(Comic(path="issue.cbz", series_name="Series", issue_number="1"))
    assert panel.count_label.text() == "1 item"
    assert panel.clear_btn.isEnabled()
    assert panel.save_btn.isEnabled()
    assert panel.export_btn.isEnabled()

    panel.clear_list()
    assert panel.count_label.text() == "0 items"
    assert not panel.clear_btn.isEnabled()
    assert not panel.save_btn.isEnabled()
    assert not panel.export_btn.isEnabled()


def test_drag_reorder_moves_row_to_top(panel):
    panel.add_comic(Comic(path="a.cbz", series_name="A", issue_number="1"))
    panel.add_comic(Comic(path="b.cbz", series_name="B", issue_number="2"))
    panel.add_comic(Comic(path="c.cbz", series_name="C", issue_number="3"))
    model = panel._table_model
    assert model.moveRows(QModelIndex(), 2, 1, QModelIndex(), 0)
    assert [comic.series_name for comic in panel.reading_list.comics] == ["C", "A", "B"]
    assert panel.reading_list.ordered_by == "manual"


def test_export_uses_current_name_for_filename(panel, monkeypatch):
    panel.name_label.setText("My New List")
    panel.header.commit_name()
    panel.add_comic(Comic(path="issue.cbz", series_name="Series", issue_number="1"))
    requested = []
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName",
        lambda *args: (requested.append(args[2]) or ("", "")),
    )
    panel.export_cbl()

    assert requested == ["My_New_List.cbl"]


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("CON", "_CON"),
        ("nul.cbl", "_nul.cbl"),
        ("Com1.txt", "_Com1.txt"),
        ("LPT9.archive", "_LPT9.archive"),
        ("PRN", "_PRN"),
        ("CLOCK$.log", "CLOCK_.log"),
        ("reading\\list/name", "reading_list_name"),
        ("Weekly Picks", "Weekly_Picks"),
    ],
)
def test_safe_filename_handles_reserved_names_separators_and_normal_names(
    panel, name, expected
):
    assert panel._safe_filename(name) == expected


def test_empty_export_is_blocked_with_feedback(panel, monkeypatch):
    requested = []
    messages = []
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: requested.append(args))
    panel.status_message.connect(messages.append)

    panel.export_cbl()

    assert requested == []
    assert messages == ["Nothing to export: the reading list is empty"]


def test_export_cancel_does_not_change_dirty_state(panel, monkeypatch):
    panel.add_comic(Comic(path="issue.cbz", series_name="Series", issue_number="1"))
    messages = []
    panel.status_message.connect(messages.append)
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: ("", ""))

    panel.export_cbl()

    assert panel.is_dirty is True
    assert messages == []


def test_export_success_clears_dirty_and_reports_status(panel, monkeypatch):
    panel.name_label.setText("Weekly: Picks / 2026")
    panel.header.commit_name()
    panel.add_comic(Comic(path="issue.cbz", series_name="Series", issue_number="1"))
    requested = []
    messages = []
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName",
        lambda *args: (requested.append(args[2]) or ("/tmp/weekly.cbl", "")),
    )
    monkeypatch.setattr("comicdesk.ui.reading_list_panel.save_cbl", lambda *_args: None)
    panel.status_message.connect(messages.append)

    panel.export_cbl()

    assert requested == ["Weekly_Picks_2026.cbl"]
    assert panel.is_dirty is False
    assert messages == ["Exported reading list to /tmp/weekly.cbl"]


def test_save_without_import_path_uses_export_dialog(panel, monkeypatch):
    panel.add_comic(Comic(path="issue.cbz", series_name="Series", issue_number="1"))
    requested = []
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        lambda *args: (requested.append(args[2]) or ("/tmp/saved.cbl", "")),
    )
    monkeypatch.setattr("comicdesk.ui.reading_list_panel.save_cbl", lambda *_args: None)
    panel.save_list()
    assert requested == ["New_Reading_List.cbl"]
    assert panel._source_cbl_path is None


def test_save_writes_imported_cbl_path(panel, monkeypatch, tmp_path):
    comic = Comic(path="issue.cbz", series_name="Series", issue_number="1")
    document = CBLDocument(
        name="Imported",
        books=[_book_for_comic(comic)],
        ordered_by="manual",
        order_direction="asc",
    )
    result = ReconciliationResult(matches=[comic], new_issues=[], missing_files=[])
    cbl_path = tmp_path / "reading.cbl"
    panel.set_available_comics([comic])
    _stub_import(monkeypatch, document, result, path=str(cbl_path))
    panel.import_cbl()
    assert panel._source_cbl_path == cbl_path

    written = []
    monkeypatch.setattr(
        "comicdesk.ui.reading_list_panel.save_cbl",
        lambda _xml, path: written.append(path),
    )
    messages = []
    panel.status_message.connect(messages.append)
    panel.save_list()

    assert written == [cbl_path]
    assert panel.is_dirty is False
    assert messages == [f"Saved reading list to {cbl_path}"]


def test_export_filesystem_error_is_reported(panel, monkeypatch):
    panel.add_comic(Comic(path="issue.cbz", series_name="Series", issue_number="1"))
    messages = []
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: ("/tmp/fail.cbl", ""))

    def fail(*_args):
        raise PermissionError("permission denied")

    monkeypatch.setattr("comicdesk.ui.reading_list_panel.save_cbl", fail)
    panel.status_message.connect(messages.append)

    panel.export_cbl()

    assert panel.is_dirty is True
    assert messages == ["Export failed: permission denied"]


def test_export_shortcut_is_preserved(qapp):
    window = MainWindow()
    try:
        file_menu = next(
            action.menu() for action in window.menuBar().actions()
            if action.text().replace("&", "") == "File"
        )
        export = next(
            action for action in file_menu.actions()
            if action.text().replace("&", "") == "Export CBL"
        )
        assert export.shortcut().toString() == "Ctrl+E"
        assert window.export_action is export
    finally:
        window.close()


def test_import_action_is_in_file_menu_and_uses_import_shortcut(qapp):
    window = MainWindow()
    try:
        file_menu = next(
            action.menu() for action in window.menuBar().actions()
            if action.text().replace("&", "") == "File"
        )
        import_action = next(
            action for action in file_menu.actions()
            if action.text().replace("&", "") == "Import CBL"
        )
        assert import_action.shortcut().toString() == "Ctrl+I"
        assert window.import_action is import_action
    finally:
        window.close()


def test_import_cancelled_at_file_dialog_keeps_current_list(panel, monkeypatch):
    comic = Comic(path="current.cbz", series_name="Current", issue_number="1")
    panel.add_comic(comic)
    panel.name_label.setText("Current List")
    panel.header.commit_name()
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args: ("", ""))
    panel.import_cbl()
    assert panel.reading_list.name == "Current List"
    assert panel.reading_list.comics == [comic]
    assert panel.is_dirty is True

def test_import_parse_error_reports_failure_without_replacing_list(panel, monkeypatch):
    comic = Comic(path="current.cbz", series_name="Current", issue_number="1")
    panel.add_comic(comic)
    messages = []
    panel.status_message.connect(messages.append)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args: ("broken.cbl", ""))
    monkeypatch.setattr(
        "comicdesk.ui.reading_list_panel.read_cbl",
        lambda _path: (_ for _ in ()).throw(CBLParseError("Invalid CBL XML")),
    )

    panel.import_cbl()
    assert panel.reading_list.comics == [comic]
    assert messages == ["Import failed: Invalid CBL XML"]

def test_dirty_import_confirmation_mentions_unsaved_changes_and_can_be_declined(
    panel, monkeypatch
):
    comic = Comic(path="current.cbz", series_name="Current", issue_number="1")
    panel.add_comic(comic)
    prompts = []
    def decline(_parent, _title, text, *_args):
        prompts.append(text)
        return QMessageBox.StandardButton.No

    _stub_import(
        monkeypatch, CBLDocument("Imported", []), ReconciliationResult([], [], []),
        QMessageBox.StandardButton.No, "next.cbl",
    )
    monkeypatch.setattr(QMessageBox, "question", decline)
    panel.import_cbl()
    assert prompts and "unsaved changes" in prompts[0]
    assert panel.reading_list.name == "New Reading List"
    assert panel.reading_list.comics == [comic]
    assert panel.is_dirty is True

def test_import_yes_explicitly_replaces_existing_list(panel, monkeypatch):
    current = Comic(path="current.cbz", series_name="Current", issue_number="1", volume="1")
    imported = Comic(path="imported.cbz", series_name="Imported", issue_number="2", volume="1")
    panel.add_comic(current)
    panel.set_available_comics([imported])
    _stub_import(
        monkeypatch,
        CBLDocument("Imported List", [_book_for_comic(imported)], "manual", "asc"),
        ReconciliationResult([imported], [], []),
        path="next.cbl",
    )

    panel.import_cbl()
    assert panel.reading_list.name == "Imported List"
    assert panel.reading_list.comics == [imported]
    assert panel.count_label.text() == "1 item"
    assert panel.is_dirty is True

def test_import_syncs_sorted_controls_from_document(panel, monkeypatch):
    imported = Comic(path="imported.cbz", series_name="Imported", issue_number="2", volume="1")
    panel.set_available_comics([imported])
    _stub_import(
        monkeypatch,
        CBLDocument("Sorted", [_book_for_comic(imported)], "title", "desc"),
        ReconciliationResult([imported], [], []),
        path="sorted.cbl",
    )

    panel.import_cbl()
    assert panel.reading_list.ordered_by == "title"
    assert panel.sort_combo.currentData() == "title"
    assert panel.direction_combo.currentData() == "desc"


def test_import_syncs_manual_control_from_document(panel, monkeypatch):
    imported = Comic(path="imported.cbz", series_name="Imported", issue_number="2", volume="1")
    panel.set_available_comics([imported])
    _stub_import(
        monkeypatch,
        CBLDocument("Manual", [_book_for_comic(imported)], "manual", "asc"),
        ReconciliationResult([imported], [], []),
        path="manual.cbl",
    )

    panel.import_cbl()
    assert panel.reading_list.ordered_by == "manual"
    assert panel.sort_controls.state_label.text() == "Custom order"
def test_importing_empty_list_replaces_contents_and_updates_controls(panel, monkeypatch):
    panel.add_comic(Comic(path="current.cbz", series_name="Current", issue_number="1"))
    messages = []
    panel.status_message.connect(messages.append)
    _stub_import(
        monkeypatch, CBLDocument("Empty List", []), ReconciliationResult([], [], []),
        path="empty.cbl",
    )

    panel.import_cbl()
    assert panel.reading_list.name == "Empty List"
    assert panel.reading_list.comics == []
    assert panel.count_label.text() == "0 items"
    assert panel.clear_btn.isEnabled() is False
    assert panel.export_btn.isEnabled() is False
    assert messages == ["Imported reading list: 0 linked, 0 not in library"]


def test_import_adds_missing_items_to_wishlist(panel, monkeypatch, tmp_path):
    wishlist = WishlistManager(path=tmp_path / "wishlist.json")
    panel.set_wishlist_manager(wishlist)
    missing = CBLBook(series_name="Missing", issue_number="3", cv_issue_id="42")
    imported = Comic(path="found.cbz", series_name="Found", issue_number="1", volume="1")
    found_book = _book_for_comic(imported)
    panel.set_available_comics([imported])
    _stub_import(
        monkeypatch,
        CBLDocument("Mixed", [found_book, missing]),
        ReconciliationResult([imported], [], [missing]),
    )

    panel.import_cbl()

    assert len(wishlist.items()) == 1
    assert wishlist.items()[0].cv_issue_id == "42"
    assert len(panel.reading_list.comics) == 2
    assert panel.reading_list.comics[0].has_local_file
    assert str(panel.reading_list.comics[0].path).endswith("found.cbz")
    assert not panel.reading_list.comics[1].has_local_file


def test_import_skips_duplicate_wishlist_items(panel, monkeypatch, tmp_path):
    wishlist = WishlistManager(path=tmp_path / "wishlist.json")
    missing = CBLBook(series_name="Missing", issue_number="3", cv_issue_id="42")
    wishlist.add_books([missing])
    panel.set_wishlist_manager(wishlist)
    imported = Comic(path="found.cbz", series_name="Found", issue_number="1", volume="1")
    panel.set_available_comics([imported])
    _stub_import(
        monkeypatch,
        CBLDocument("Mixed", [_book_for_comic(imported), missing]),
        ReconciliationResult([imported], [], [missing]),
    )

    panel.import_cbl()

    assert len(wishlist.items()) == 1


def test_import_does_not_touch_wishlist_when_declined(panel, monkeypatch, tmp_path):
    wishlist = WishlistManager(path=tmp_path / "wishlist.json")
    panel.set_wishlist_manager(wishlist)
    missing = CBLBook(series_name="Missing", issue_number="3", cv_issue_id="42")
    _stub_import(
        monkeypatch,
        CBLDocument("Mixed", [missing]),
        ReconciliationResult([], [], [missing]),
        wishlist_answer=QMessageBox.StandardButton.No,
    )

    panel.import_cbl()

    assert wishlist.items() == []
    assert len(panel.reading_list.comics) == 1
    assert not panel.reading_list.comics[0].has_local_file


def test_import_keeps_missing_entries_in_reading_list(panel, monkeypatch):
    missing = CBLBook(series_name="Missing", issue_number="9")
    imported = Comic(path="found.cbz", series_name="Found", issue_number="1", volume="1")
    panel.set_available_comics([imported])
    _stub_import(
        monkeypatch,
        CBLDocument("Mixed", [_book_for_comic(imported), missing]),
        ReconciliationResult([imported], [], [missing]),
        wishlist_answer=QMessageBox.StandardButton.No,
    )

    panel.import_cbl()

    assert len(panel.reading_list.comics) == 2
    assert panel._cell_text(1, panel._COL_FILE) == "Not in library"


def test_import_all_matched_does_not_show_extra_information_dialog(panel, monkeypatch):
    info_calls = []
    comic = Comic(path="found.cbz", series_name="Found", issue_number="1", volume="1")
    book = CBLBook(series_name="Found", issue_number="1", volume="1")
    panel.set_available_comics([comic])
    _stub_import(
        monkeypatch,
        CBLDocument("Complete", [book]),
        ReconciliationResult([comic], [], []),
    )
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda *args: info_calls.append(args[2]),
    )

    panel.import_cbl()

    assert info_calls == []


def test_reading_list_displays_series_name_not_title(panel):
    comic = Comic(
        path="avengers.cbz",
        series_name="Avengers",
        title="The Avengers assemble",
        issue_number="22",
        year="2023",
    )
    panel.add_comic(comic)

    assert panel._cell_text(0, panel._COL_SERIES) == "Avengers"
    assert panel._cell_text(0, panel._COL_ISSUE) == "22"
    assert panel._cell_text(0, panel._COL_TITLE) == "The Avengers assemble"


def test_reading_list_displays_release_date(panel):
    comic = Comic(
        path="spidey.cbz",
        series_name="Amazing Spider-Man",
        issue_number="700",
        year="2013",
        month="7",
        day="4",
    )
    panel.add_comic(comic)

    assert panel._cell_text(0, panel._COL_SERIES) == "Amazing Spider-Man"
    assert panel._cell_text(0, panel._COL_ISSUE) == "700"
    assert panel._cell_text(0, panel._COL_RELEASE) == "2013-07-04"


# --- Tests for last CBL directory persistence ---


@pytest.fixture
def config_panel(qapp, tmp_path):
    config = Config(default_folder=str(tmp_path / "default_cbl"))
    widget = ReadingListPanel(config=config)
    yield widget
    widget.close()


def test_import_uses_last_cbl_directory_as_start_path(config_panel, monkeypatch, tmp_path):
    last_dir = tmp_path / "last_import"
    last_dir.mkdir()
    config_panel.config.last_cbl_directory = str(last_dir)

    requested = []
    monkeypatch.setattr(
        QFileDialog, "getOpenFileName",
        lambda *args: (requested.append(args[2]) or ("", "")),
    )
    config_panel.import_cbl()

    assert requested == [str(last_dir)]


def test_export_uses_last_cbl_directory_as_start_path(config_panel, monkeypatch, tmp_path):
    last_dir = tmp_path / "last_export"
    last_dir.mkdir()
    config_panel.config.last_cbl_directory = str(last_dir)
    config_panel.name_label.setText("My List")
    config_panel.header.commit_name()
    config_panel.add_comic(
        Comic(path="issue.cbz", series_name="Series", issue_number="1")
    )

    requested = []
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName",
        lambda *args: (requested.append(args[2]) or ("", "")),
    )
    config_panel.export_cbl()

    assert requested == [str(last_dir / "My_List.cbl")]


def test_import_persists_selected_directory(config_panel, monkeypatch, tmp_path):
    selected_dir = tmp_path / "chosen"
    selected_dir.mkdir()
    selected_file = selected_dir / "test.cbl"

    monkeypatch.setattr(
        QFileDialog, "getOpenFileName",
        lambda *args: (str(selected_file), ""),
    )
    monkeypatch.setattr(
        "comicdesk.ui.reading_list_panel.read_cbl",
        lambda _path: CBLDocument("Empty", []),
    )
    monkeypatch.setattr(
        "comicdesk.ui.reading_list_panel.reconcile_cbl",
        lambda _doc, _comics: ReconciliationResult([], [], []),
    )
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)

    config_panel.import_cbl()

    assert config_panel.config.last_cbl_directory == str(selected_dir)


def test_export_persists_selected_directory(config_panel, monkeypatch, tmp_path):
    selected_dir = tmp_path / "export_dir"
    selected_dir.mkdir()
    selected_file = selected_dir / "exported.cbl"

    config_panel.add_comic(
        Comic(path="issue.cbz", series_name="Series", issue_number="1")
    )
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName",
        lambda *args: (str(selected_file), ""),
    )
    monkeypatch.setattr("comicdesk.ui.reading_list_panel.save_cbl", lambda *_a: None)

    config_panel.export_cbl()

    assert config_panel.config.last_cbl_directory == str(selected_dir)


def test_falls_back_to_default_folder_when_no_last_directory(qapp, tmp_path):
    default_dir = tmp_path / "default"
    default_dir.mkdir()
    config = Config(default_folder=str(default_dir))
    widget = ReadingListPanel(config=config)
    try:
        requested = []
        monkeypatch_target = __import__("unittest.mock", fromlist=["patch"]).patch(
            "PySide6.QtWidgets.QFileDialog.getOpenFileName",
            side_effect=lambda *args: (requested.append(args[2]) or ("", "")),
        )
        with monkeypatch_target:
            widget.import_cbl()
        assert requested == [str(default_dir)]
    finally:
        widget.close()


def test_first_use_with_empty_config_uses_system_default(qapp):
    config = Config()
    widget = ReadingListPanel(config=config)
    try:
        requested = []
        monkeypatch_target = __import__("unittest.mock", fromlist=["patch"]).patch(
            "PySide6.QtWidgets.QFileDialog.getOpenFileName",
            side_effect=lambda *args: (requested.append(args[2]) or ("", "")),
        )
        with monkeypatch_target:
            widget.import_cbl()
        assert requested == [""]
    finally:
        widget.close()


def test_import_cancels_without_persisting(config_panel, monkeypatch, tmp_path):
    config_panel.config.last_cbl_directory = ""
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args: ("", ""))

    config_panel.import_cbl()

    assert config_panel.config.last_cbl_directory == ""


def test_export_cancels_without_persisting(config_panel, monkeypatch, tmp_path):
    config_panel.config.last_cbl_directory = ""
    config_panel.add_comic(
        Comic(path="issue.cbz", series_name="Series", issue_number="1")
    )
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: ("", ""))

    config_panel.export_cbl()

    assert config_panel.config.last_cbl_directory == ""
