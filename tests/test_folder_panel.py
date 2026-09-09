"""Tests for FolderPanel workspace folder sorting."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


def test_folder_tree_sorting_enabled(qapp):
    from comicdesk.ui.folder_panel import FolderPanel

    panel = FolderPanel()
    try:
        assert panel.tree.isSortingEnabled()
    finally:
        panel.close()
