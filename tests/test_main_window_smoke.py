"""Offscreen construction smoke test for the main workspace."""

import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

import comicdesk.config as config_module
from comicdesk.ui.main_window import MainWindow
from comicdesk.ui.theme import colors_for


@pytest.fixture
def qapp():
    """Provide the application instance required by Qt widgets."""
    return QApplication.instance() or QApplication([])


def test_main_window_builds_offscreen(qapp):
    """MainWindow exposes all workspace panels and core tabs."""
    window = MainWindow()

    assert window.splitter.count() == 3
    assert window.folder_panel is window.splitter.widget(0)
    assert window.comic_list is window.splitter.widget(1)
    assert window.reading_list_panel is window.splitter.widget(2)
    assert window.tabs.count() == 4
    assert window.tabs.tabText(1) == "Metadata"
    assert window.tabs.tabText(2) == "GetComics"
    assert window.tabs.tabText(3) == "Downloads"
    assert window.metadata_panel is window.tabs.widget(1)
    assert window.getcomics_panel is window.tabs.widget(2)
    assert window.download_queue_panel is window.tabs.widget(3)
    assert window.menuBar().actions()
    # A configured existing default folder starts scanning during construction;
    # that status is real feedback and must not be suppressed for the smoke test.
    status = window.statusbar.currentMessage()
    assert status == "Ready" or status.startswith("Scanning: ")

    window.close()


def test_main_window_focuses_comic_in_metadata_tab(qapp):
    window = MainWindow()
    from pathlib import Path
    from comicdesk.models import Comic

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


def test_main_window_applies_light_theme(qapp, tmp_path, monkeypatch):
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"theme": "light"}), encoding="utf-8")
    monkeypatch.setattr(config_module, "CONFIG_FILE", config_file)

    window = MainWindow()

    assert window.config.theme == "light"
    app_stylesheet = QApplication.instance().styleSheet()
    assert colors_for("light")["canvas"] in app_stylesheet
    window.close()
