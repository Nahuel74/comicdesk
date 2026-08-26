"""Behaviour tests for the read-only CBL preview widget and integration."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from cbl_maker.models import Comic
from cbl_maker.ui.cbl_preview import CBLPreview
from cbl_maker.ui.reading_list_panel import ReadingListPanel


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


def test_preview_empty_and_actions(qapp):
    preview = CBLPreview()
    preview.set_content("")
    assert preview.toPlainText() == ""
    preview.select_all()
    preview.copy()


def test_panel_regenerates_with_current_name_and_comics(qapp):
    panel = ReadingListPanel()
    panel.add_comic(Comic(path="one.cbz", series_name="Current Series", issue_number="7"))
    assert "Current Series" in panel.preview.toPlainText()
    panel.name_label.setText("Renamed")
    panel.header.commit_name()
    assert "Renamed" in panel.preview.toPlainText()
    panel._move_down(0)
    panel._remove_at(0)
    assert panel.preview.toPlainText() == ""
    panel.close()


def test_expanded_state_survives_refresh(qapp):
    panel = ReadingListPanel()
    panel.preview.set_expanded(False)
    panel.add_comic(Comic(path="one.cbz", series_name="Series", issue_number="1"))
    assert not panel.preview.is_expanded()
    panel.preview.set_expanded(True)
    panel.preview.maximize()
    assert panel.preview.is_expanded()
    panel.close()
