"""Tests for the download queue manager."""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from comicdesk.config import Config
from comicdesk.models import Comic
from comicdesk.services.download_queue import DownloadQueueManager, DownloadStatus
from comicdesk.services.getcomics import GetComicsDownloadLink, GetComicsIssue


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


def _make_issue(title: str = "Test Comic") -> GetComicsIssue:
    return GetComicsIssue(
        title=title,
        url=f"https://getcomics.org/comics/{title.lower().replace(' ', '-')}/",
        download_links=[
            GetComicsDownloadLink("MAIN SERVER", "MAIN SERVER", "https://getcomics.org/dls/main/"),
        ],
    )


def test_enqueue_multiple_pending(qapp, tmp_path):
    manager = DownloadQueueManager(config=Config())
    with patch.object(manager, "_process_next"):
        id1 = manager.enqueue(_make_issue("One"), tmp_path)
        id2 = manager.enqueue(_make_issue("Two"), tmp_path)
    assert len(manager.items()) == 2
    assert manager.get_item(id1).status == DownloadStatus.PENDING
    assert manager.get_item(id2).status == DownloadStatus.PENDING


def test_cancel_pending_item(qapp, tmp_path):
    manager = DownloadQueueManager(config=Config())
    with patch.object(manager, "_start_item"):
        item_id = manager.enqueue(_make_issue(), tmp_path)
    manager.cancel(item_id)
    assert manager.get_item(item_id).status == DownloadStatus.CANCELLED


def test_clear_completed(qapp, tmp_path):
    manager = DownloadQueueManager(config=Config())
    with patch.object(manager, "_start_item"):
        item_id = manager.enqueue(_make_issue(), tmp_path)
    manager.get_item(item_id).status = DownloadStatus.COMPLETED
    manager.clear_completed()
    assert manager.get_item(item_id) is None


def test_retry_error_item(qapp, tmp_path):
    manager = DownloadQueueManager(config=Config())
    with patch.object(manager, "_start_item") as start_item:
        item_id = manager.enqueue(_make_issue(), tmp_path)
        item = manager.get_item(item_id)
        item.status = DownloadStatus.ERROR
        item.error_message = "failed"
        manager.retry(item_id)
    assert manager.get_item(item_id).status == DownloadStatus.PENDING
    start_item.assert_called()


def test_sequential_processing_on_finish(qapp, tmp_path):
    manager = DownloadQueueManager(config=Config())
    issue1 = _make_issue("First")
    issue2 = _make_issue("Second")
    comic = Comic(Path("first.cbz"))

    with patch("comicdesk.services.download_queue.GetComicsDownloadWorker") as worker_cls:
        worker1 = MagicMock()
        worker1.isRunning.return_value = True
        worker_cls.return_value = worker1

        id1 = manager.enqueue(issue1, tmp_path)
        id2 = manager.enqueue(issue2, tmp_path)

        assert manager.get_item(id1).status == DownloadStatus.RUNNING
        assert manager.get_item(id2).status == DownloadStatus.PENDING

        manager._on_finished(manager.get_item(id1), comic, worker1)

        assert manager.get_item(id1).status == DownloadStatus.COMPLETED
        assert worker_cls.call_count == 2
        assert manager.get_item(id2).status == DownloadStatus.RUNNING


def test_manual_links_pauses_queue(qapp, tmp_path):
    manager = DownloadQueueManager(config=Config())
    links = [
        GetComicsDownloadLink("MEGA", "MEGA", "https://getcomics.org/dls/mega/"),
    ]

    with patch("comicdesk.services.download_queue.GetComicsDownloadWorker") as worker_cls:
        worker = MagicMock()
        worker_cls.return_value = worker
        item_id = manager.enqueue(_make_issue(), tmp_path)
        item = manager.get_item(item_id)

        received = []
        manager.manual_links_required.connect(
            lambda i, l: received.append((i, l))
        )
        manager._on_manual_links_required(item, links, worker)

    assert manager.get_item(item_id).status == DownloadStatus.NEEDS_ATTENTION
    assert received == [(item_id, links)]
    assert manager._paused is True


def test_resolve_manual_resumes_queue(qapp, tmp_path):
    manager = DownloadQueueManager(config=Config())
    link = GetComicsDownloadLink("MAIN SERVER", "MAIN SERVER", "https://getcomics.org/dls/main/")

    with patch.object(manager, "_start_item") as start_item:
        with patch("comicdesk.services.download_queue.GetComicsDownloadWorker"):
            item_id = manager.enqueue(_make_issue(), tmp_path)
        item = manager.get_item(item_id)
        item.status = DownloadStatus.NEEDS_ATTENTION
        manager._paused = True
        manager.resolve_manual(item_id, link)

    assert manager.get_item(item_id).status == DownloadStatus.PENDING
    assert manager.get_item(item_id).selected_link is link
    assert manager._paused is False
    start_item.assert_called()
