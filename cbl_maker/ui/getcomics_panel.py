"""GetComics search and download panel."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from cbl_maker.config import Config
from cbl_maker.services.getcomics import GetComicsDownloadLink, GetComicsIssue, GetComicsSearchResult
from cbl_maker.ui.getcomics_workers import (
    GetComicsDownloadWorker,
    GetComicsIssueWorker,
    GetComicsSearchWorker,
    GetComicsThumbnailWorker,
)
from cbl_maker.ui.theme import COLORS, SPACING

logger = logging.getLogger(__name__)


class DownloadLinksDialog(QDialog):
    """Let the user pick a provider when automatic download is unavailable."""

    def __init__(self, links: list[GetComicsDownloadLink], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select download provider")
        self.setMinimumWidth(420)
        self._links = links
        self.selected_link: GetComicsDownloadLink | None = None

        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel("No direct download link was found. Choose a provider to open in your browser:")
        )
        self.list_widget = QListWidget()
        for link in links:
            item = QListWidgetItem(f"{link.provider} — {link.label}")
            item.setData(Qt.ItemDataRole.UserRole, link)
            self.list_widget.addItem(item)
        self.list_widget.itemDoubleClicked.connect(self._accept_selection)
        layout.addWidget(self.list_widget)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept_selection)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _accept_selection(self):
        item = self.list_widget.currentItem()
        if item is None:
            QMessageBox.warning(self, "Selection required", "Please select a download link.")
            return
        self.selected_link = item.data(Qt.ItemDataRole.UserRole)
        self.accept()


class GetComicsPanel(QWidget):
    status_message = Signal(str)
    download_completed = Signal(object)

    def __init__(self, config: Config | None = None, parent=None):
        super().__init__(parent)
        self.config = config
        self._search_worker: GetComicsSearchWorker | None = None
        self._issue_worker: GetComicsIssueWorker | None = None
        self._download_worker: GetComicsDownloadWorker | None = None
        self._thumbnail_worker: GetComicsThumbnailWorker | None = None
        self._thumbnail_token = 0
        self._current_issue: GetComicsIssue | None = None
        self._current_page = 1
        self._last_query = ""
        self._last_criterion = "name"
        self._build_ui()

    def _build_ui(self):
        self.setObjectName("getComicsPanel")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(*(SPACING["md"] for _ in range(4)))
        outer.setSpacing(SPACING["sm"])

        title = QLabel("GetComics")
        title.setStyleSheet(f"font-size: 15px; font-weight: 600; color: {COLORS['text']};")
        outer.addWidget(title)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, SPACING["sm"], 0)

        search_group = QGroupBox("Search")
        search_form = QFormLayout(search_group)
        self.criterion_combo = QComboBox()
        self.criterion_combo.addItem("Name", "name")
        self.criterion_combo.addItem("Category", "category")
        self.criterion_combo.addItem("Tag", "tag")
        search_form.addRow("Criterion", self.criterion_combo)

        query_row = QHBoxLayout()
        self.query_input = QLineEdit()
        self.query_input.setPlaceholderText("Search query or slug...")
        self.query_input.returnPressed.connect(lambda: self._start_search())
        self.search_button = QPushButton("Search")
        self.search_button.clicked.connect(lambda: self._start_search())
        query_row.addWidget(self.query_input)
        query_row.addWidget(self.search_button)
        search_form.addRow("Query", query_row)

        page_row = QHBoxLayout()
        self.prev_page_button = QPushButton("Previous")
        self.prev_page_button.clicked.connect(self._previous_page)
        self.page_label = QLabel("Page 1")
        self.next_page_button = QPushButton("Next")
        self.next_page_button.clicked.connect(self._next_page)
        page_row.addWidget(self.prev_page_button)
        page_row.addWidget(self.page_label, 1, Qt.AlignmentFlag.AlignCenter)
        page_row.addWidget(self.next_page_button)
        search_form.addRow("", page_row)
        left_layout.addWidget(search_group)

        self.results_list = QListWidget()
        self.results_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.results_list.currentItemChanged.connect(self._on_result_selected)
        left_layout.addWidget(self.results_list, 1)

        dest_group = QGroupBox("Download destination")
        dest_layout = QHBoxLayout(dest_group)
        self.dest_input = QLineEdit(self._default_download_folder())
        self.dest_browse_button = QPushButton("Browse...")
        self.dest_browse_button.clicked.connect(self._browse_dest_folder)
        dest_layout.addWidget(self.dest_input)
        dest_layout.addWidget(self.dest_browse_button)
        left_layout.addWidget(dest_group)

        self.enrich_checkbox = QCheckBox("Enrich from Comic Vine after download")
        self.enrich_checkbox.setChecked(self._auto_enrich_enabled())
        left_layout.addWidget(self.enrich_checkbox)

        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self.detail_title = QLabel("Select a result to view details")
        self.detail_title.setWordWrap(True)
        self.detail_title.setStyleSheet(f"font-weight: 600; color: {COLORS['text']};")
        right_layout.addWidget(self.detail_title)

        meta_row = QHBoxLayout()
        self.thumbnail_label = QLabel()
        self.thumbnail_label.setFixedSize(120, 180)
        self.thumbnail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumbnail_label.setStyleSheet(
            f"background: {COLORS['surface']}; border: 1px solid {COLORS['border']};"
        )
        meta_col = QVBoxLayout()
        self.detail_date = QLabel("")
        self.detail_date.setStyleSheet(f"color: {COLORS['muted']};")
        self.detail_excerpt = QLabel("")
        self.detail_excerpt.setWordWrap(True)
        meta_col.addWidget(self.detail_date)
        meta_col.addWidget(self.detail_excerpt)
        meta_row.addWidget(self.thumbnail_label)
        meta_row.addLayout(meta_col, 1)
        right_layout.addLayout(meta_row)

        self.links_table = QTableWidget(0, 3)
        self.links_table.setHorizontalHeaderLabels(["Provider", "Label", "Auto"])
        self.links_table.horizontalHeader().setStretchLastSection(True)
        self.links_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.links_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        right_layout.addWidget(self.links_table, 1)

        action_row = QHBoxLayout()
        self.download_button = QPushButton("Download")
        self.download_button.clicked.connect(lambda: self._start_download())
        self.download_button.setEnabled(False)
        self.cancel_download_button = QPushButton("Cancel")
        self.cancel_download_button.clicked.connect(self._cancel_download)
        self.cancel_download_button.setVisible(False)
        self.browser_button = QPushButton("Open in browser")
        self.browser_button.clicked.connect(self._open_selected_in_browser)
        self.browser_button.setEnabled(False)
        action_row.addWidget(self.download_button)
        action_row.addWidget(self.cancel_download_button)
        action_row.addWidget(self.browser_button)
        action_row.addStretch()
        right_layout.addLayout(action_row)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        right_layout.addWidget(self.progress_bar)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet(f"color: {COLORS['muted']};")
        right_layout.addWidget(self.status_label)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([360, 640])
        outer.addWidget(splitter, 1)

        self.setStyleSheet(
            f"QWidget#getComicsPanel {{ background: {COLORS['canvas']}; color: {COLORS['text']}; }}"
            f" QLineEdit, QComboBox, QListWidget, QTableWidget {{"
            f" background: {COLORS['surface']}; color: {COLORS['text']};"
            f" border: 1px solid {COLORS['border']}; border-radius: 4px; }}"
        )

    def _default_download_folder(self) -> str:
        if self.config is None:
            return ""
        folder = getattr(self.config, "getcomics_download_folder", "") or ""
        if folder:
            return folder
        return self.config.default_folder or ""

    def _auto_enrich_enabled(self) -> bool:
        if self.config is None:
            return True
        return bool(getattr(self.config, "auto_enrich_after_download", True))

    def set_config(self, config: Config):
        self.config = config
        if not self.dest_input.text().strip():
            self.dest_input.setText(self._default_download_folder())
        self.enrich_checkbox.setChecked(self._auto_enrich_enabled())

    def _browse_dest_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select download folder", self.dest_input.text()
        )
        if folder:
            self.dest_input.setText(folder)

    def _start_search(self, page: int | None = None):
        query = self.query_input.text().strip()
        if not query:
            QMessageBox.warning(self, "Search", "Enter a search query.")
            return
        criterion = self.criterion_combo.currentData()
        self._last_query = query
        self._last_criterion = criterion
        if page is None:
            self._current_page = 1
        else:
            self._current_page = page
        logger.info(
            "getcomics_action_search criterion=%s query=%s page=%d",
            criterion,
            query,
            self._current_page,
        )
        self._set_busy(True, "Searching...")
        self._stop_search_worker()
        self._search_worker = GetComicsSearchWorker(criterion, query, self._current_page)
        worker = self._search_worker
        worker.finished.connect(lambda results, w=worker: self._on_search_finished(results, w))
        worker.error.connect(lambda message, w=worker: self._on_search_error(message, w))
        worker.start()

    def _previous_page(self):
        if self._current_page <= 1 or not self._last_query:
            return
        self._start_search(page=self._current_page - 1)

    def _next_page(self):
        if not self._last_query:
            return
        self._start_search(page=self._current_page + 1)

    def _on_search_finished(self, results: list[GetComicsSearchResult], worker):
        if worker is not self._search_worker:
            return
        self._set_busy(False)
        self.results_list.clear()
        self._clear_detail()
        for result in results:
            item = QListWidgetItem(result.title)
            item.setData(Qt.ItemDataRole.UserRole, result)
            self.results_list.addItem(item)
        self.page_label.setText(f"Page {self._current_page}")
        message = f"Found {len(results)} result(s)"
        self.status_label.setText(message)
        self.status_message.emit(message)
        logger.info("getcomics_action_search_finished result_count=%d", len(results))

    def _on_search_error(self, message: str, worker):
        if worker is not self._search_worker:
            return
        self._set_busy(False)
        self.status_label.setText(message)
        self.status_message.emit(message)
        QMessageBox.warning(self, "GetComics search failed", message)

    def _on_result_selected(self, current: QListWidgetItem | None, _previous):
        if current is None:
            return
        result = current.data(Qt.ItemDataRole.UserRole)
        if not isinstance(result, GetComicsSearchResult):
            return
        self.detail_title.setText(result.title)
        self.detail_date.setText(result.date)
        self.detail_excerpt.setText(result.excerpt)
        logger.info("getcomics_action_issue_selected title=%s url=%s", result.title, result.url)
        self._load_thumbnail(result.thumbnail_url)
        self._set_busy(True, "Loading issue details...")
        self._stop_issue_worker()
        self._issue_worker = GetComicsIssueWorker(result.url)
        worker = self._issue_worker
        worker.finished.connect(lambda issue, w=worker: self._on_issue_loaded(issue, w))
        worker.error.connect(lambda message, w=worker: self._on_issue_error(message, w))
        worker.start()

    def _on_issue_loaded(self, issue: GetComicsIssue, worker):
        if worker is not self._issue_worker:
            return
        self._set_busy(False)
        self._current_issue = issue
        self.detail_title.setText(issue.title)
        self.detail_date.setText(issue.date)
        self.detail_excerpt.setText(issue.excerpt)
        self._load_thumbnail(issue.thumbnail_url)
        self._populate_links_table(issue.download_links)
        self.download_button.setEnabled(True)
        self.browser_button.setEnabled(True)
        self.status_label.setText(f"{len(issue.download_links)} download link(s) found")
        logger.info(
            "getcomics_action_issue_loaded title=%s link_count=%d",
            issue.title,
            len(issue.download_links),
        )

    def _on_issue_error(self, message: str, worker):
        if worker is not self._issue_worker:
            return
        self._set_busy(False)
        self.status_label.setText(message)
        QMessageBox.warning(self, "GetComics issue failed", message)

    def _populate_links_table(self, links: list[GetComicsDownloadLink]):
        self.links_table.setRowCount(len(links))
        for row, link in enumerate(links):
            self.links_table.setItem(row, 0, QTableWidgetItem(link.provider))
            self.links_table.setItem(row, 1, QTableWidgetItem(link.label))
            auto_item = QTableWidgetItem("Yes" if link.is_auto_downloadable else "No")
            auto_item.setData(Qt.ItemDataRole.UserRole, link)
            self.links_table.setItem(row, 2, auto_item)

    def _selected_link(self) -> GetComicsDownloadLink | None:
        row = self.links_table.currentRow()
        if row < 0:
            return None
        item = self.links_table.item(row, 2)
        if item is None:
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def _dest_path(self) -> Path | None:
        folder = self.dest_input.text().strip()
        if not folder:
            QMessageBox.warning(self, "Download folder", "Select a download destination folder.")
            return None
        path = Path(folder)
        if not path.exists():
            QMessageBox.warning(self, "Download folder", "The selected folder does not exist.")
            return None
        return path

    def _start_download(self, selected_link: GetComicsDownloadLink | None = None):
        if self._current_issue is None:
            return
        if self._download_worker is not None and self._download_worker.isRunning():
            QMessageBox.warning(
                self,
                "Download in progress",
                "Wait for the current download to finish before starting another one.",
            )
            return
        dest = self._dest_path()
        if dest is None:
            return
        api_key = self.config.api_key if self.config else ""
        cache_enabled = self.config.cache_enabled if self.config else True
        auto_enrich = self.enrich_checkbox.isChecked()
        logger.info(
            "getcomics_action_download_started issue=%s dest_dir=%s auto_enrich=%s selected_provider=%s",
            self._current_issue.url,
            dest,
            auto_enrich,
            getattr(selected_link, "provider", None),
        )
        self._set_download_active(True, "Starting download...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self._download_worker = GetComicsDownloadWorker(
            self._current_issue,
            dest,
            api_key=api_key,
            cache_enabled=cache_enabled,
            auto_enrich=auto_enrich,
            selected_link=selected_link,
        )
        worker = self._download_worker
        worker.progress.connect(self._on_download_progress)
        worker.finished.connect(lambda comic, w=worker: self._on_download_finished(comic, w))
        worker.error.connect(lambda message, w=worker: self._on_download_error(message, w))
        worker.manual_links_required.connect(
            lambda links, w=worker: self._on_manual_links_required(links, w)
        )
        worker.cancelled.connect(lambda w=worker: self._on_download_cancelled(w))
        worker.start()

    def _set_download_active(self, active: bool, message: str = ""):
        self.download_button.setEnabled(not active and self._current_issue is not None)
        self.cancel_download_button.setVisible(active)
        self.cancel_download_button.setEnabled(active)
        self.browser_button.setEnabled(not active and self._current_issue is not None)
        self.search_button.setEnabled(not active)
        if message:
            self.status_label.setText(message)

    def _cancel_download(self):
        worker = self._download_worker
        if worker is None or not worker.isRunning():
            return
        logger.info(
            "getcomics_action_download_cancel issue=%s",
            getattr(self._current_issue, "url", ""),
        )
        worker.cancel()
        self.cancel_download_button.setEnabled(False)
        self.status_label.setText("Cancelling download...")
        self.status_message.emit("Cancelling download...")

    def _on_download_progress(self, current: int, total: int, message: str):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        self.status_label.setText(message)
        self.status_message.emit(message)

    def _on_download_finished(self, comic, worker):
        if worker is not self._download_worker:
            return
        self._set_download_active(False)
        self.progress_bar.setVisible(False)
        message = f"Saved to {comic.path}"
        self.status_label.setText(message)
        self.status_message.emit(message)
        self.download_completed.emit(comic)
        logger.info("getcomics_action_download_finished path=%s", comic.path)
        worker.deleteLater()
        self._download_worker = None

    def _on_download_cancelled(self, worker):
        if worker is not self._download_worker:
            return
        self._set_download_active(False)
        self.progress_bar.setVisible(False)
        self.status_label.setText("Download cancelled")
        self.status_message.emit("Download cancelled")
        logger.info("getcomics_action_download_cancelled")
        worker.deleteLater()
        self._download_worker = None

    def _on_download_error(self, message: str, worker):
        if worker is not self._download_worker:
            return
        self._set_download_active(False)
        self.progress_bar.setVisible(False)
        self.status_label.setText(message)
        self.status_message.emit(message)
        logger.warning("getcomics_action_download_failed message=%s", message)
        QMessageBox.warning(self, "Download failed", message)
        worker.deleteLater()
        self._download_worker = None

    def _on_manual_links_required(self, links: list[GetComicsDownloadLink], worker):
        if worker is not self._download_worker:
            return
        self._set_download_active(False)
        self.progress_bar.setVisible(False)
        worker.deleteLater()
        self._download_worker = None
        logger.info("getcomics_action_manual_links_required link_count=%d", len(links))
        dialog = DownloadLinksDialog(links, self)
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.selected_link is None:
            self.status_label.setText("Manual provider selection cancelled")
            return
        link = dialog.selected_link
        if link.is_auto_downloadable:
            self._start_download(selected_link=link)
            return
        answer = QMessageBox.question(
            self,
            "Open in browser",
            f"Open {link.provider} in your browser for manual download?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            logger.info("getcomics_action_open_browser provider=%s url=%s", link.provider, link.url)
            QDesktopServices.openUrl(QUrl(link.url))
            self.status_message.emit(f"Opened {link.provider} in browser")

    def _open_selected_in_browser(self):
        link = self._selected_link()
        if link is None:
            if self._current_issue is not None and self._current_issue.url:
                QDesktopServices.openUrl(QUrl(self._current_issue.url))
            return
        answer = QMessageBox.question(
            self,
            "Open in browser",
            f"Open {link.provider} in your browser?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            logger.info(
                "getcomics_action_open_browser provider=%s url=%s",
                link.provider,
                link.url,
            )
            QDesktopServices.openUrl(QUrl(link.url))

    def _load_thumbnail(self, url: str):
        self._stop_thumbnail_worker()
        self.thumbnail_label.clear()
        if not url:
            return
        self._thumbnail_token += 1
        token = self._thumbnail_token
        self._thumbnail_worker = GetComicsThumbnailWorker(url, token=token)
        worker = self._thumbnail_worker
        worker.finished.connect(
            lambda data, t=token, w=worker: self._on_thumbnail_loaded(data, t, w)
        )
        worker.error.connect(lambda _message, w=worker: self._on_thumbnail_error(w))
        worker.start()

    def _on_thumbnail_loaded(self, data: bytes, token: int, worker):
        if worker is not self._thumbnail_worker or token != self._thumbnail_token:
            return
        pixmap = QPixmap()
        if not pixmap.loadFromData(data):
            self.thumbnail_label.setText("No preview")
            return
        scaled = pixmap.scaled(
            self.thumbnail_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.thumbnail_label.setPixmap(scaled)

    def _on_thumbnail_error(self, worker):
        if worker is not self._thumbnail_worker:
            return
        self.thumbnail_label.setText("No preview")

    def _clear_detail(self):
        self._current_issue = None
        self.detail_title.setText("Select a result to view details")
        self.detail_date.clear()
        self.detail_excerpt.clear()
        self._stop_thumbnail_worker()
        self.thumbnail_label.clear()
        self.links_table.setRowCount(0)
        self.download_button.setEnabled(False)
        self.browser_button.setEnabled(False)

    def _set_busy(self, busy: bool, message: str = ""):
        self.search_button.setEnabled(not busy)
        self.download_button.setEnabled(not busy and self._current_issue is not None)
        if message:
            self.status_label.setText(message)

    def _stop_search_worker(self):
        worker = self._search_worker
        if worker is None:
            return
        worker.cancel()
        if worker.isRunning():
            worker.wait(5000)
        worker.deleteLater()
        self._search_worker = None

    def _stop_issue_worker(self):
        worker = self._issue_worker
        if worker is None:
            return
        worker.cancel()
        if worker.isRunning():
            worker.wait(5000)
        worker.deleteLater()
        self._issue_worker = None

    def _stop_download_worker(self):
        worker = self._download_worker
        if worker is None:
            return
        worker.cancel()
        if worker.isRunning():
            worker.wait()
        worker.deleteLater()
        self._download_worker = None

    def _stop_thumbnail_worker(self):
        worker = self._thumbnail_worker
        if worker is None:
            return
        worker.cancel()
        if worker.isRunning():
            worker.wait(5000)
        worker.deleteLater()
        self._thumbnail_worker = None

    def shutdown_workers(self):
        logger.info("getcomics_action_shutdown_workers")
        self._stop_search_worker()
        self._stop_issue_worker()
        self._stop_download_worker()
        self._stop_thumbnail_worker()
