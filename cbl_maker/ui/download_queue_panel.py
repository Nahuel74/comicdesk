"""Download queue management panel."""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from cbl_maker.config import Config
from cbl_maker.services.download_queue import DownloadQueueManager, DownloadStatus
from cbl_maker.ui.getcomics_panel import DownloadLinksDialog
from cbl_maker.ui.theme import (
    SPACING,
    button_stylesheet,
    colors_for,
    download_queue_panel_stylesheet,
    menu_stylesheet,
    muted_label_stylesheet,
    table_stylesheet,
)

logger = logging.getLogger(__name__)

_STATUS_LABELS = {
    DownloadStatus.PENDING: "Pending",
    DownloadStatus.RUNNING: "Running",
    DownloadStatus.COMPLETED: "Completed",
    DownloadStatus.ERROR: "Error",
    DownloadStatus.CANCELLED: "Cancelled",
    DownloadStatus.NEEDS_ATTENTION: "Needs attention",
}

_PROGRESS_COLUMN_WIDTH = 110
_STATUS_COLUMN_WIDTH = 110


def _progress_label(item) -> str:
    if item.status == DownloadStatus.RUNNING:
        return f"{item.progress}%"
    if item.status == DownloadStatus.COMPLETED:
        return "100%"
    if item.status == DownloadStatus.PENDING:
        return "—"
    if item.status == DownloadStatus.ERROR:
        return "Failed"
    if item.status == DownloadStatus.CANCELLED:
        return "—"
    if item.status == DownloadStatus.NEEDS_ATTENTION:
        return "—"
    return ""


def _detail_text(item) -> str:
    if item.error_message:
        return item.error_message
    if item.status_message:
        return item.status_message
    return ""


class DownloadQueuePanel(QWidget):
    """Panel for viewing and managing the download queue."""

    status_message = Signal(str)

    def __init__(self, queue: DownloadQueueManager, config: Config | None = None, parent=None):
        super().__init__(parent)
        self.queue = queue
        self.config = config
        self._theme = "dark"
        self._build_ui()
        self._connect_queue()

    def _build_ui(self) -> None:
        self.setObjectName("downloadQueuePanel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(*(SPACING["md"] for _ in range(4)))
        layout.setSpacing(SPACING["sm"])

        header_row = QHBoxLayout()
        self.title_label = QLabel("Downloads")
        header_row.addWidget(self.title_label)
        header_row.addStretch()
        self.count_label = QLabel("")
        header_row.addWidget(self.count_label)
        self.clear_completed_button = QPushButton("Clear completed")
        self.clear_completed_button.clicked.connect(self._clear_completed)
        header_row.addWidget(self.clear_completed_button)
        layout.addLayout(header_row)

        self.hint_label = QLabel("Right-click a row for actions")
        layout.addWidget(self.hint_label)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Status", "Title", "Progress"])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        header.resizeSection(0, _STATUS_COLUMN_WIDTH)
        header.resizeSection(2, _PROGRESS_COLUMN_WIDTH)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self.table, 1)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.apply_theme(self._theme)

    def _connect_queue(self) -> None:
        self.queue.item_added.connect(self._refresh_table)
        self.queue.item_updated.connect(self._update_row)
        self.queue.item_removed.connect(self._refresh_table)
        self.queue.queue_changed.connect(self._update_counts)
        self.queue.manual_links_required.connect(self._on_manual_links_required)

    def apply_theme(self, theme: str) -> None:
        self._theme = theme
        c = colors_for(theme)
        self.setStyleSheet(download_queue_panel_stylesheet(theme))
        self.table.setStyleSheet(table_stylesheet(theme))
        self.title_label.setStyleSheet(
            f"font-size: 15px; font-weight: 600; color: {c['text']};"
        )
        self.hint_label.setStyleSheet(muted_label_stylesheet(theme))
        self.count_label.setStyleSheet(muted_label_stylesheet(theme))
        self.status_label.setStyleSheet(muted_label_stylesheet(theme))
        default_btn = button_stylesheet(theme, "default")
        self.clear_completed_button.setStyleSheet(default_btn)

    def set_config(self, config: Config) -> None:
        self.config = config
        self.queue.set_config(config)

    def shutdown_workers(self) -> None:
        self.queue.shutdown()

    def _item_id_at_row(self, row: int) -> str | None:
        if row < 0:
            return None
        cell = self.table.item(row, 1)
        if cell is None:
            return None
        item_id = cell.data(Qt.ItemDataRole.UserRole)
        return item_id if isinstance(item_id, str) else None

    def _item_at_row(self, row: int):
        item_id = self._item_id_at_row(row)
        if item_id is None:
            return None
        return self.queue.get_item(item_id)

    def _refresh_table(self, _item_id: str = "") -> None:
        items = self.queue.items()
        self.table.setRowCount(len(items))
        for row, item in enumerate(items):
            self._fill_row(row, item)
        self._update_counts()
        self._on_selection_changed()

    def _update_row(self, item_id: str) -> None:
        item = self.queue.get_item(item_id)
        if item is None:
            self._refresh_table()
            return
        for row in range(self.table.rowCount()):
            if self._item_id_at_row(row) == item_id:
                self._fill_row(row, item)
                self._update_counts()
                self._on_selection_changed()
                return
        self._refresh_table()

    def _fill_row(self, row: int, item) -> None:
        status_text = _STATUS_LABELS.get(item.status, str(item.status))
        status_item = QTableWidgetItem(status_text)
        status_item.setData(Qt.ItemDataRole.UserRole, item.id)
        detail = _detail_text(item)
        if detail:
            status_item.setToolTip(detail)
        self.table.setItem(row, 0, status_item)

        title_item = QTableWidgetItem(item.issue.title)
        title_item.setData(Qt.ItemDataRole.UserRole, item.id)
        if detail:
            title_item.setToolTip(detail)
        self.table.setItem(row, 1, title_item)

        progress_item = QTableWidgetItem(_progress_label(item))
        progress_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        if detail:
            progress_item.setToolTip(detail)
        self.table.setItem(row, 2, progress_item)

    def _on_selection_changed(self) -> None:
        item = self._item_at_row(self.table.currentRow())
        if item is None:
            self.status_label.clear()
            return
        self.status_label.setText(_detail_text(item))

    def _show_context_menu(self, position) -> None:
        row = self.table.rowAt(position.y())
        if row < 0:
            return
        self.table.selectRow(row)
        item = self._item_at_row(row)
        if item is None:
            return

        menu = QMenu(self)
        menu.setStyleSheet(menu_stylesheet(self._theme))
        item_id = item.id

        if item.status in (DownloadStatus.PENDING, DownloadStatus.RUNNING):
            menu.addAction("Cancel download", lambda: self._cancel_item(item_id))
        if item.status in (
            DownloadStatus.ERROR,
            DownloadStatus.CANCELLED,
            DownloadStatus.NEEDS_ATTENTION,
        ):
            menu.addAction("Retry download", lambda: self._retry_item(item_id))
        if item.status not in (DownloadStatus.RUNNING, DownloadStatus.NEEDS_ATTENTION):
            menu.addAction("Remove from queue", lambda: self._remove_item(item_id))

        if menu.actions():
            menu.addSeparator()

        menu.addAction("Copy GetComics URL", lambda: self._copy_text(item.issue.url))

        if item.issue.download_links:
            links_menu = menu.addMenu("Copy download link")
            links_menu.setStyleSheet(menu_stylesheet(self._theme))
            for link in item.issue.download_links:
                label = link.provider or link.label or "Link"
                links_menu.addAction(label, lambda url=link.url: self._copy_text(url))
            menu.addAction(
                "Copy all download links",
                lambda: self._copy_text(self._format_download_links(item)),
            )

        if item.result_comic is not None:
            menu.addSeparator()
            menu.addAction(
                "Copy saved file path",
                lambda: self._copy_text(str(item.result_comic.path)),
            )

        menu.exec(self.table.viewport().mapToGlobal(position))

    def _format_download_links(self, item) -> str:
        lines = []
        for link in item.issue.download_links:
            label = link.provider or link.label or "Link"
            lines.append(f"{label}: {link.url}")
        return "\n".join(lines)

    def _copy_text(self, text: str) -> None:
        if not text:
            return
        QApplication.clipboard().setText(text)
        self.status_message.emit("Copied to clipboard")

    def _update_counts(self) -> None:
        items = self.queue.items()
        pending = sum(1 for i in items if i.status == DownloadStatus.PENDING)
        running = sum(1 for i in items if i.status == DownloadStatus.RUNNING)
        done = sum(1 for i in items if i.status == DownloadStatus.COMPLETED)
        attention = sum(1 for i in items if i.status == DownloadStatus.NEEDS_ATTENTION)
        parts = []
        if pending:
            parts.append(f"{pending} pending")
        if running:
            parts.append(f"{running} running")
        if attention:
            parts.append(f"{attention} need attention")
        if done:
            parts.append(f"{done} completed")
        self.count_label.setText(", ".join(parts) if parts else "Queue empty")

    def _clear_completed(self) -> None:
        self.queue.clear_completed()
        self._refresh_table()
        self.status_message.emit("Cleared completed downloads")

    def _cancel_item(self, item_id: str) -> None:
        self.queue.cancel(item_id)
        self.status_message.emit("Download cancelled")

    def _retry_item(self, item_id: str) -> None:
        self.queue.retry(item_id)
        self.status_message.emit("Download re-queued")

    def _remove_item(self, item_id: str) -> None:
        self.queue.remove(item_id)
        self._refresh_table()

    def _on_manual_links_required(self, item_id: str, links: list) -> None:
        self._refresh_table()
        parent = self.window() or self
        dialog = DownloadLinksDialog(links, parent, theme=self._theme)
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.selected_link is None:
            self.queue.mark_manual_cancelled(item_id, "Provider selection cancelled")
            self.status_message.emit("Provider selection cancelled")
            return
        link = dialog.selected_link
        if link.is_auto_downloadable:
            self.queue.resolve_manual(item_id, link)
            self.status_message.emit(f"Resuming download via {link.provider}")
            return
        answer = QMessageBox.question(
            self,
            "Open in browser",
            f"Open {link.provider} in your browser for manual download?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            QDesktopServices.openUrl(QUrl(link.url))
            self.queue.mark_manual_cancelled(
                item_id,
                f"Opened {link.provider} in browser for manual download",
            )
            self.status_message.emit(f"Opened {link.provider} in browser")
        else:
            self.queue.mark_manual_cancelled(item_id, "Manual download not started")
