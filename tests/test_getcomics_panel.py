"""Offscreen smoke tests for the GetComics panel."""

import os
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QItemSelectionModel, QUrl
from PySide6.QtWidgets import QApplication

from comicdesk.config import Config
from comicdesk.models import CBLBook
from comicdesk.services.download_queue import DownloadQueueManager
from comicdesk.services.getcomics import GetComicsDownloadLink, GetComicsIssue
from comicdesk.services.wishlist import WishlistManager
from comicdesk.ui.getcomics_panel import DownloadLinksDialog, GetComicsPanel
from comicdesk.ui.getcomics_workers import GetComicsIssueWorker


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


def test_panel_smoke_offscreen(qapp):
    panel = GetComicsPanel(config=Config())
    assert panel.criterion_combo.count() == 3
    assert panel.download_button.isEnabled() is False
    assert not hasattr(panel, "enrich_checkbox")
    assert panel.open_issue_button.isEnabled() is False
    assert panel.wishlist_table.columnCount() == 4
    assert panel.wishlist_count_label.text() == "0 items"
    panel.shutdown_workers()


def test_wishlist_table_refreshes_from_manager(qapp, tmp_path):
    panel = GetComicsPanel(config=Config())
    manager = WishlistManager(path=tmp_path / "wishlist.json")
    panel.set_wishlist_manager(manager)
    manager.add_books([CBLBook(series_name="Batman", issue_number="1")])
    assert panel.wishlist_table.rowCount() == 1
    assert panel.wishlist_table.item(0, 0).text() == "Batman"
    panel.shutdown_workers()


def test_manual_links_dialog_lists_providers(qapp):
    links = [
        GetComicsDownloadLink("MEGA", "MEGA", "https://getcomics.org/dls/mega/"),
        GetComicsDownloadLink("PIXELDRAIN", "PIXELDRAIN", "https://getcomics.org/dls/pd/"),
    ]
    dialog = DownloadLinksDialog(links)
    assert dialog.list_widget.count() == 2
    dialog.list_widget.setCurrentRow(1)
    dialog._accept_selection()
    assert dialog.selected_link is links[1]


def test_issue_loaded_preserves_search_excerpt(qapp):
    panel = GetComicsPanel(config=Config())
    search_excerpt = "Summary from search results."
    issue = GetComicsIssue(
        title="Test",
        url="https://getcomics.org/comics/test/",
        excerpt="",
        download_links=[
            GetComicsDownloadLink("MAIN SERVER", "MAIN SERVER", "https://getcomics.org/dls/main/"),
        ],
    )
    panel._pending_excerpt = search_excerpt
    panel.detail_excerpt.setText(search_excerpt)
    worker = GetComicsIssueWorker(issue.url)
    panel._issue_worker = worker
    panel._on_issue_loaded(issue, worker)
    assert panel.detail_excerpt.text() == search_excerpt
    panel.shutdown_workers()


def test_start_download_enqueues_and_shows_progress(qapp, tmp_path):
    panel = GetComicsPanel(config=Config())
    queue = DownloadQueueManager(config=Config())
    panel.set_download_queue(queue)
    issue = GetComicsIssue(
        title="Test",
        url="https://getcomics.org/comics/test/",
        download_links=[
            GetComicsDownloadLink("MAIN SERVER", "MAIN SERVER", "https://getcomics.org/dls/main/"),
        ],
    )
    panel._current_issue = issue
    panel.dest_input.setText(str(tmp_path))

    panel.show()
    with patch.object(queue, "enqueue", return_value="abc123") as enqueue:
        panel._start_download()

    enqueue.assert_called_once()
    assert enqueue.call_args.kwargs == {"selected_link": None}
    assert panel.progress_bar.isVisible()
    assert panel._tracked_download_id == "abc123"
    panel.shutdown_workers()


def test_open_on_getcomics_uses_issue_url_when_link_selected(qapp):
    panel = GetComicsPanel(config=Config())
    issue_url = "https://getcomics.org/comics/test/"
    dls_url = "https://getcomics.org/dls/main/"
    issue = GetComicsIssue(
        title="Test",
        url=issue_url,
        download_links=[
            GetComicsDownloadLink("MAIN SERVER", "MAIN SERVER", dls_url),
        ],
    )
    panel._current_issue = issue
    panel._populate_links_table(issue.download_links)
    panel.links_table.selectRow(0)
    panel.open_issue_button.setEnabled(True)

    with patch("comicdesk.ui.getcomics_panel.QDesktopServices.openUrl") as open_url:
        panel._open_issue_on_getcomics()

    open_url.assert_called_once()
    assert open_url.call_args[0][0] == QUrl(issue_url)
    panel.shutdown_workers()


def test_provider_browser_button_with_row_selection_only(qapp):
    panel = GetComicsPanel(config=Config())
    issue = GetComicsIssue(
        title="Test",
        url="https://getcomics.org/comics/test/",
        download_links=[
            GetComicsDownloadLink("MAIN SERVER", "MAIN SERVER", "https://getcomics.org/dls/main/"),
        ],
    )
    panel._populate_links_table(issue.download_links)
    selection_model = panel.links_table.selectionModel()
    selection_model.select(
        panel.links_table.model().index(0, 0),
        QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows,
    )
    assert panel.links_table.currentRow() < 0
    assert panel._selected_link() is not None
    assert panel.browser_button.isEnabled()
    panel.shutdown_workers()
