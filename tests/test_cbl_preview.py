"""Behaviour tests for the read-only CBL preview widget and integration."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from comicdesk.models import Comic
from comicdesk.ui.cbl_preview import CBLPreview
from comicdesk.ui.reading_list_panel import ReadingListPanel


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
    panel.table.selectRow(0)
    panel._remove_selected()
    assert panel.preview.toPlainText() == ""
    panel.close()


def test_preview_updates_after_list_changes(qapp):
    panel = ReadingListPanel()
    panel.add_comic(Comic(path="one.cbz", series_name="Series", issue_number="1"))
    assert "Series" in panel.preview.toPlainText()
    panel.add_comic(Comic(path="two.cbz", series_name="Other", issue_number="2"))
    assert "Series" in panel.preview.toPlainText()
    assert "Other" in panel.preview.toPlainText()
    panel._remove_at(0)
    xml = panel.preview.toPlainText()
    assert 'SeriesName="Series"' not in xml
    assert 'SeriesName="Other"' in xml
    panel.close()
