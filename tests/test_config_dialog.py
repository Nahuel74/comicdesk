"""Smoke tests for the settings dialog."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from comicdesk.config import Config
from comicdesk.ui.config_dialog import ConfigDialog


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


def test_config_dialog_builds_offscreen(qapp):
    dialog = ConfigDialog(Config())
    assert dialog.title_label.text() == "Settings"
    assert dialog.theme_combo.count() == 2
