"""Download queue orchestration for GetComics downloads."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Signal

from comicdesk.models import Comic
from comicdesk.services.getcomics import GetComicsDownloadLink, GetComicsIssue
from comicdesk.ui.getcomics_workers import GetComicsDownloadWorker

if TYPE_CHECKING:
    from comicdesk.config import Config

logger = logging.getLogger(__name__)


class DownloadStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    ERROR = "error"
    CANCELLED = "cancelled"
    NEEDS_ATTENTION = "needs_attention"


@dataclass
class DownloadQueueItem:
    """A single queued GetComics download job."""

    id: str
    issue: GetComicsIssue
    dest_dir: Path
    selected_link: GetComicsDownloadLink | None = None
    status: DownloadStatus = DownloadStatus.PENDING
    progress: int = 0
    status_message: str = ""
    error_message: str = ""
    result_comic: Comic | None = None


class DownloadQueueManager(QObject):
    """Sequential download queue backed by GetComicsDownloadWorker."""

    item_added = Signal(str)
    item_updated = Signal(str)
    item_removed = Signal(str)
    queue_changed = Signal()
    download_completed = Signal(object)
    manual_links_required = Signal(str, list)

    def __init__(self, config: Config | None = None, parent=None):
        super().__init__(parent)
        self.config = config
        self._items: list[DownloadQueueItem] = []
        self._active_worker: GetComicsDownloadWorker | None = None
        self._active_item_id: str | None = None
        self._paused = False
        self._shutting_down = False

    def items(self) -> list[DownloadQueueItem]:
        return list(self._items)

    def get_item(self, item_id: str) -> DownloadQueueItem | None:
        for item in self._items:
            if item.id == item_id:
                return item
        return None

    def enqueue(
        self,
        issue: GetComicsIssue,
        dest_dir: Path,
        *,
        selected_link: GetComicsDownloadLink | None = None,
    ) -> str:
        item_id = uuid.uuid4().hex[:12]
        item = DownloadQueueItem(
            id=item_id,
            issue=issue,
            dest_dir=Path(dest_dir),
            selected_link=selected_link,
            status=DownloadStatus.PENDING,
            status_message="Waiting in queue",
        )
        self._items.append(item)
        logger.info(
            "download_queue_enqueue id=%s issue=%s dest=%s",
            item_id,
            issue.url,
            dest_dir,
        )
        self.item_added.emit(item_id)
        self.queue_changed.emit()
        self._process_next()
        return item_id

    def cancel(self, item_id: str) -> None:
        item = self.get_item(item_id)
        if item is None:
            return
        if item.status == DownloadStatus.PENDING:
            item.status = DownloadStatus.CANCELLED
            item.status_message = "Cancelled"
            self.item_updated.emit(item_id)
            self.queue_changed.emit()
            logger.info("download_queue_cancel_pending id=%s", item_id)
            return
        if item_id == self._active_item_id and self._active_worker is not None:
            logger.info("download_queue_cancel_active id=%s", item_id)
            self._active_worker.cancel()

    def cancel_active(self) -> None:
        if self._active_item_id is not None:
            self.cancel(self._active_item_id)

    def remove(self, item_id: str) -> None:
        item = self.get_item(item_id)
        if item is None:
            return
        if item.status in (DownloadStatus.RUNNING, DownloadStatus.NEEDS_ATTENTION):
            return
        self._items = [i for i in self._items if i.id != item_id]
        self.item_removed.emit(item_id)
        self.queue_changed.emit()

    def clear_completed(self) -> None:
        removed = [i.id for i in self._items if i.status == DownloadStatus.COMPLETED]
        self._items = [i for i in self._items if i.status != DownloadStatus.COMPLETED]
        for item_id in removed:
            self.item_removed.emit(item_id)
        if removed:
            self.queue_changed.emit()

    def retry(self, item_id: str) -> None:
        item = self.get_item(item_id)
        if item is None:
            return
        if item.status not in (DownloadStatus.ERROR, DownloadStatus.CANCELLED, DownloadStatus.NEEDS_ATTENTION):
            return
        item.status = DownloadStatus.PENDING
        item.progress = 0
        item.status_message = "Waiting in queue"
        item.error_message = ""
        item.result_comic = None
        item.selected_link = None
        self.item_updated.emit(item_id)
        self.queue_changed.emit()
        self._process_next()

    def resolve_manual(self, item_id: str, link: GetComicsDownloadLink) -> None:
        item = self.get_item(item_id)
        if item is None:
            return
        if item.status != DownloadStatus.NEEDS_ATTENTION:
            return
        item.selected_link = link
        item.status = DownloadStatus.PENDING
        item.status_message = "Waiting in queue"
        item.error_message = ""
        self._paused = False
        self.item_updated.emit(item_id)
        self.queue_changed.emit()
        self._process_next()

    def mark_manual_cancelled(self, item_id: str, message: str = "Manual provider selected") -> None:
        item = self.get_item(item_id)
        if item is None:
            return
        item.status = DownloadStatus.ERROR
        item.error_message = message
        item.status_message = message
        self._paused = False
        self.item_updated.emit(item_id)
        self.queue_changed.emit()
        self._process_next()

    def set_config(self, config: Config) -> None:
        self.config = config

    def shutdown(self) -> None:
        self._shutting_down = True
        worker = self._active_worker
        if worker is not None:
            worker.cancel()
            if worker.isRunning():
                worker.wait(5000)
            worker.deleteLater()
            self._active_worker = None
        self._active_item_id = None

    def _process_next(self) -> None:
        if self._shutting_down or self._paused:
            return
        if self._active_worker is not None and self._active_worker.isRunning():
            return
        for item in self._items:
            if item.status == DownloadStatus.PENDING:
                self._start_item(item)
                return

    def _start_item(self, item: DownloadQueueItem) -> None:
        item.status = DownloadStatus.RUNNING
        item.progress = 0
        item.status_message = "Starting download..."
        self._active_item_id = item.id
        self.item_updated.emit(item.id)
        self.queue_changed.emit()

        worker = GetComicsDownloadWorker(
            item.issue,
            item.dest_dir,
            selected_link=item.selected_link,
        )
        self._active_worker = worker
        worker.progress.connect(lambda c, t, m, i=item: self._on_progress(i, c, t, m))
        worker.finished.connect(lambda comic, w=worker, i=item: self._on_finished(i, comic, w))
        worker.error.connect(lambda message, w=worker, i=item: self._on_error(i, message, w))
        worker.cancelled.connect(lambda w=worker, i=item: self._on_cancelled(i, w))
        worker.manual_links_required.connect(
            lambda links, w=worker, i=item: self._on_manual_links_required(i, links, w)
        )
        worker.start()
        logger.info("download_queue_start id=%s issue=%s", item.id, item.issue.url)

    def _on_progress(self, item: DownloadQueueItem, current: int, total: int, message: str) -> None:
        if item.id != self._active_item_id:
            return
        item.progress = current
        item.status_message = message
        self.item_updated.emit(item.id)

    def _on_finished(self, item: DownloadQueueItem, comic: Comic, worker: GetComicsDownloadWorker) -> None:
        if worker is not self._active_worker or item.id != self._active_item_id:
            return
        item.status = DownloadStatus.COMPLETED
        item.progress = 100
        item.result_comic = comic
        item.status_message = f"Saved to {comic.path}"
        self._cleanup_worker(worker)
        self.item_updated.emit(item.id)
        self.queue_changed.emit()
        self.download_completed.emit(comic)
        logger.info("download_queue_finished id=%s path=%s", item.id, comic.path)
        self._process_next()

    def _on_error(self, item: DownloadQueueItem, message: str, worker: GetComicsDownloadWorker) -> None:
        if worker is not self._active_worker or item.id != self._active_item_id:
            return
        item.status = DownloadStatus.ERROR
        item.error_message = message
        item.status_message = message
        self._cleanup_worker(worker)
        self.item_updated.emit(item.id)
        self.queue_changed.emit()
        logger.warning("download_queue_error id=%s message=%s", item.id, message)
        self._process_next()

    def _on_cancelled(self, item: DownloadQueueItem, worker: GetComicsDownloadWorker) -> None:
        if worker is not self._active_worker or item.id != self._active_item_id:
            return
        item.status = DownloadStatus.CANCELLED
        item.status_message = "Download cancelled"
        self._cleanup_worker(worker)
        self.item_updated.emit(item.id)
        self.queue_changed.emit()
        logger.info("download_queue_cancelled id=%s", item.id)
        self._process_next()

    def _on_manual_links_required(
        self,
        item: DownloadQueueItem,
        links: list[GetComicsDownloadLink],
        worker: GetComicsDownloadWorker,
    ) -> None:
        if worker is not self._active_worker or item.id != self._active_item_id:
            return
        item.status = DownloadStatus.NEEDS_ATTENTION
        item.status_message = "Manual provider selection required"
        self._paused = True
        self._cleanup_worker(worker)
        self.item_updated.emit(item.id)
        self.queue_changed.emit()
        self.manual_links_required.emit(item.id, links)
        logger.info("download_queue_needs_attention id=%s link_count=%d", item.id, len(links))

    def _cleanup_worker(self, worker: GetComicsDownloadWorker) -> None:
        worker.deleteLater()
        if worker is self._active_worker:
            self._active_worker = None
            self._active_item_id = None
