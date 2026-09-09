"""Offscreen smoke tests for the GetComics panel."""

import os
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from cbl_maker.config import Config
from cbl_maker.models import Comic
from cbl_maker.services.getcomics import GetComicsDownloadLink, GetComicsIssue
from cbl_maker.ui.getcomics_panel import DownloadLinksDialog, GetComicsPanel


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


def test_shutdown_workers_stops_active_thread(qapp):
    panel = GetComicsPanel(config=Config())
    issue = GetComicsIssue(
        title="Test",
        url="https://getcomics.org/comics/test/",
        download_links=[
            GetComicsDownloadLink("MAIN SERVER", "MAIN SERVER", "https://getcomics.org/dls/main/"),
        ],
    )
    panel._current_issue = issue
    panel.dest_input.setText(str(Path.cwd()))

    with patch("cbl_maker.ui.getcomics_workers.GetComicsClient") as client_cls:
        client = client_cls.return_value.__enter__.return_value
        client.pick_auto_download_link.return_value = issue.download_links[0]
        client.resolve_redirect.return_value = "https://getcomics.org/files/test.cbz"
        client.download_file.return_value = Path("test.cbz")

        with patch(
            "cbl_maker.ui.getcomics_workers._build_comic_from_download",
            return_value=Comic(Path("test.cbz")),
        ):
            panel._start_download()
            panel.shutdown_workers()

    assert panel._download_worker is None
