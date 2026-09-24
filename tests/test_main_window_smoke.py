"""Offscreen construction smoke test for the main workspace."""

import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

import comicdesk.config as config_module
from comicdesk.ui.main_window import MainWindow
from comicdesk.ui.shell.primary_nav import NAV_ACQUIRE, NAV_LIBRARY, NAV_METADATA, NAV_PAGES
from comicdesk.ui.theme import colors_for


@pytest.fixture
def qapp():
    """Provide the application instance required by Qt widgets."""
    return QApplication.instance() or QApplication([])


def test_main_window_builds_offscreen(qapp):
    """MainWindow exposes the app shell, panels, and workflow stack."""
    window = MainWindow()

    assert window.app_shell is not None
    assert window.folder_panel is window.folder_sidebar.folder_panel
    assert window.comic_list is window.app_shell.comic_list
    assert window.reading_list_panel is window.app_shell.reading_list_panel
    assert window.metadata_panel is window.app_shell.metadata_panel
    assert window.pages_panel is window.app_shell.pages_panel
    assert window.getcomics_panel is window.app_shell.getcomics_panel
    assert window.download_queue_panel is window.app_shell.download_queue_panel
    assert window.app_shell.stack.count() == 5
    assert window.menuBar().actions()
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
    assert window.app_shell.current_nav_id() == NAV_METADATA
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


def test_main_window_lists_attention_after_add(qapp):
    from pathlib import Path
    from comicdesk.models import Comic

    window = MainWindow()
    comic = Comic(Path("book.cbz"), series_name="Test", issue_number="1")
    window.reading_list_panel.add_comic(comic)
    window.app_shell.notify_lists_attention(1)
    lists_button = window.app_shell.primary_nav._buttons["lists"]
    assert lists_button.property("attention") is True
    window.app_shell.navigate_to("lists")
    assert lists_button.property("attention") in (False, None)
    window.close()


def test_folder_sidebar_hidden_on_lists(qapp):
    window = MainWindow()
    window.show()
    window.app_shell.navigate_to("lists")
    assert not window.folder_sidebar.isVisible()
    window.app_shell.navigate_to("library")
    assert window.folder_sidebar.isVisible()
    window.app_shell.navigate_to(NAV_PAGES)
    assert window.folder_sidebar.isVisible()
    window.app_shell.navigate_to(NAV_ACQUIRE)
    assert not window.folder_sidebar.isVisible()
    window.close()


def test_main_window_navigate_to_acquire(qapp):
    window = MainWindow()
    window.app_shell.navigate_to(NAV_ACQUIRE)
    assert window.app_shell.current_nav_id() == NAV_ACQUIRE
    window.app_shell.navigate_to(NAV_LIBRARY)
    assert window.app_shell.current_nav_id() == NAV_LIBRARY
    window.close()
