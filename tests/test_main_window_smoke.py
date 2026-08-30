"""Offscreen construction smoke test for the main workspace."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from cbl_maker.ui.main_window import MainWindow


@pytest.fixture
def qapp():
    """Provide the application instance required by Qt widgets."""
    return QApplication.instance() or QApplication([])


def test_main_window_builds_offscreen(qapp):
    """MainWindow exposes all three workspace panels and core actions."""
    window = MainWindow()

    assert window.splitter.count() == 3
    assert window.folder_panel is window.splitter.widget(0)
    assert window.comic_list is window.splitter.widget(1)
    assert window.reading_list_panel is window.splitter.widget(2)
    assert window.tabs.count() == 2
    assert window.tabs.tabText(1) == "Metadata"
    assert window.metadata_panel is window.tabs.widget(1)
    assert window.menuBar().actions()
    # A configured existing default folder starts scanning during construction;
    # that status is real feedback and must not be suppressed for the smoke test.
    status = window.statusbar.currentMessage()
    assert status == "Ready" or status.startswith("Scanning: ")

    window.close()


def test_main_window_focuses_comic_in_metadata_tab(qapp):
    window = MainWindow()
    from pathlib import Path
    from cbl_maker.models import Comic

    comic = Comic(Path("book.cbz"), title="Book")
    window._on_comic_focused(comic)

    assert window.metadata_panel.comic is comic
    window._open_metadata_tab(comic)
    assert window.tabs.currentWidget() is window.metadata_panel
    window.close()


def test_main_window_closes_reading_list_workers(qapp, monkeypatch):
    window = MainWindow()
    stopped = []
    monkeypatch.setattr(
        window.reading_list_panel,
        "shutdown_workers",
        lambda: stopped.append(True),
    )

    window.close()

    assert stopped == [True]
