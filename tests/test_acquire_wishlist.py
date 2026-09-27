"""Acquire area layout and wishlist wiring."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from comicdesk.models import Comic
from comicdesk.services.series_gaps import all_missing_issues_as_cbl_books, analyze_series_gaps
from comicdesk.services.comicvine_api import normalize_cv_volume_id
from comicdesk.ui.main_window import MainWindow
from comicdesk.ui.shell.primary_nav import NAV_ACQUIRE
from comicdesk.ui.shell.secondary_nav import SUB_ACQUIRE_WISHLIST


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


def test_normalize_cv_volume_id_strips_prefix():
    assert normalize_cv_volume_id("4050-170548") == "170548"
    assert normalize_cv_volume_id("170548") == "170548"


def test_acquire_stack_has_single_getcomics_widget(qapp):
    window = MainWindow()
    acquire = window.app_shell.acquire_page
    assert acquire.stack.count() == 2
    assert acquire.stack.indexOf(window.getcomics_panel) == 0
    window.close()


def test_series_wishlist_shows_rows_in_wishlist_view(qapp, tmp_path, monkeypatch):
    import comicdesk.services.wishlist as wishlist_module

    monkeypatch.setattr(wishlist_module, "WISHLIST_FILE", tmp_path / "wishlist.json")
    window = MainWindow()
    window.wishlist_manager._path = tmp_path / "wishlist.json"
    window.wishlist_manager.load()

    from pathlib import Path

    comics = [
        Comic(
            Path("a.cbz"),
            series_name="Marc Spector: Moon Knight",
            issue_number="1",
            count="3",
            cv_series_id="170548",
            volume="2026",
        ),
    ]
    books = all_missing_issues_as_cbl_books(analyze_series_gaps(comics))
    window._on_series_wishlist(books)

    assert len(window.wishlist_manager.items()) == 2
    assert window.getcomics_panel.wishlist_table.rowCount() == 2
    assert window.app_shell.acquire_page.stack.currentIndex() == 0
    window.close()
