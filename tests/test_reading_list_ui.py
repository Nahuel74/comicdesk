"""Focused tests for reading-list identity and list-level actions."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QFileDialog

from cbl_maker.models import Comic
from cbl_maker.ui.main_window import MainWindow
from cbl_maker.ui.reading_list_panel import ReadingListPanel


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def panel(qapp):
    widget = ReadingListPanel()
    yield widget
    widget.close()


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
    assert not panel.export_btn.isEnabled()

    panel.add_comic(Comic(path="issue.cbz", series_name="Series", issue_number="1"))
    assert panel.count_label.text() == "1 item"
    assert panel.clear_btn.isEnabled()
    assert panel.export_btn.isEnabled()

    panel.clear_list()
    assert panel.count_label.text() == "0 items"
    assert not panel.clear_btn.isEnabled()
    assert not panel.export_btn.isEnabled()


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
    monkeypatch.setattr("cbl_maker.ui.reading_list_panel.save_cbl", lambda *_args: None)
    panel.status_message.connect(messages.append)

    panel.export_cbl()

    assert requested == ["Weekly_Picks_2026.cbl"]
    assert panel.is_dirty is False
    assert messages == ["Exported reading list to /tmp/weekly.cbl"]


def test_export_filesystem_error_is_reported(panel, monkeypatch):
    panel.add_comic(Comic(path="issue.cbz", series_name="Series", issue_number="1"))
    messages = []
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: ("/tmp/fail.cbl", ""))

    def fail(*_args):
        raise PermissionError("permission denied")

    monkeypatch.setattr("cbl_maker.ui.reading_list_panel.save_cbl", fail)
    panel.status_message.connect(messages.append)

    panel.export_cbl()

    assert panel.is_dirty is True
    assert messages == ["Export failed: permission denied"]


def test_export_shortcut_is_preserved(qapp):
    window = MainWindow()
    try:
        export_actions = [
            action for action in window.menuBar().actions()
            if action.menu() and any(
                child.text().replace("&", "") == "Export CBL"
                for child in action.menu().actions()
            )
        ]
        assert export_actions
        export = next(
            child for child in export_actions[0].menu().actions()
            if child.text().replace("&", "") == "Export CBL"
        )
        assert export.shortcut().toString() == "Ctrl+E"
    finally:
        window.close()
