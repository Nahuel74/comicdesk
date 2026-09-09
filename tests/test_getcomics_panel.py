"""Offscreen smoke tests for the GetComics panel."""

import os
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from cbl_maker.config import Config
from cbl_maker.services.download_queue import DownloadQueueManager
from cbl_maker.services.getcomics import GetComicsDownloadLink, GetComicsIssue
from cbl_maker.ui.getcomics_panel import DownloadLinksDialog, GetComicsPanel
from cbl_maker.ui.getcomics_workers import GetComicsIssueWorker


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


def test_panel_smoke_offscreen(qapp):
    panel = GetComicsPanel(config=Config())
    assert panel.criterion_combo.count() == 3
    assert panel.download_button.isEnabled() is False
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
    assert enqueue.call_args.kwargs["selected_link"] is None
    assert panel.progress_bar.isVisible()
    assert panel._tracked_download_id == "abc123"
    panel.shutdown_workers()
