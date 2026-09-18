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
    QHeaderView,
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

from comicdesk.config import Config
from comicdesk.models import CBLBook
from comicdesk.services.download_queue import DownloadQueueManager, DownloadStatus
from comicdesk.services.cbl_display import (
    cbl_book_issue_label,
    cbl_book_series_label,
    cbl_book_volume_label,
)
from comicdesk.services.getcomics import (
    GetComicsDownloadLink,
    GetComicsIssue,
    GetComicsSearchResult,
    build_search_query,
)
from comicdesk.services.wishlist import WishlistManager
from comicdesk.ui.getcomics_workers import (
    GetComicsIssueWorker,
    GetComicsSearchWorker,
    GetComicsThumbnailWorker,
    WishlistBatchDownloadWorker,
    WishlistDownloadWorker,
)
from comicdesk.ui.theme import (
    SPACING,
    button_stylesheet,
    colors_for,
    dialog_stylesheet,
    getcomics_panel_stylesheet,
    muted_label_stylesheet,
)

logger = logging.getLogger(__name__)


class DownloadLinksDialog(QDialog):
    """Let the user pick a provider when automatic download is unavailable."""

    def __init__(self, links: list[GetComicsDownloadLink], parent=None, theme: str = "dark"):
        super().__init__(parent)
        self.setWindowTitle("Select download provider")
        self.setMinimumWidth(420)
        self._links = links
        self._theme = theme
        self.selected_link: GetComicsDownloadLink | None = None
        self.setStyleSheet(dialog_stylesheet(theme))

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

    def __init__(self, config: Config | None = None, parent=None):
        super().__init__(parent)
        self.config = config
        self._download_queue: DownloadQueueManager | None = None
        self._tracked_download_id: str | None = None
        self._search_worker: GetComicsSearchWorker | None = None
        self._issue_worker: GetComicsIssueWorker | None = None
        self._thumbnail_worker: GetComicsThumbnailWorker | None = None
        self._wishlist_worker: WishlistDownloadWorker | None = None
        self._wishlist_batch_worker: WishlistBatchDownloadWorker | None = None
        self._wishlist_manager: WishlistManager | None = None
        self._thumbnail_token = 0
        self._current_issue: GetComicsIssue | None = None
        self._pending_excerpt = ""
        self._current_page = 1
        self._last_query = ""
        self._last_criterion = "name"
        self._theme = "dark"
        self._build_ui()

    def _build_ui(self):
        self.setObjectName("getComicsPanel")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(*(SPACING["md"] for _ in range(4)))
        outer.setSpacing(SPACING["sm"])

        self.title_label = QLabel("Search GetComics")
        self.title_label.setObjectName("getComicsSectionLabel")
        outer.addWidget(self.title_label)

        search_row = QHBoxLayout()
        self.criterion_combo = QComboBox()
        self.criterion_combo.addItem("Name", "name")
        self.criterion_combo.addItem("Category", "category")
        self.criterion_combo.addItem("Tag", "tag")
        self.query_input = QLineEdit()
        self.query_input.setPlaceholderText("Search query or slug...")
        self.query_input.returnPressed.connect(lambda: self._start_search())
        self.search_button = QPushButton("Search")
        self.search_button.clicked.connect(lambda: self._start_search())
        self.prev_page_button = QPushButton("Previous")
        self.prev_page_button.clicked.connect(self._previous_page)
        self.page_label = QLabel("Page 1")
        self.next_page_button = QPushButton("Next")
        self.next_page_button.clicked.connect(self._next_page)
        search_row.addWidget(self.criterion_combo)
        search_row.addWidget(self.query_input, 1)
        search_row.addWidget(self.search_button)
        search_row.addWidget(self.prev_page_button)
        search_row.addWidget(self.page_label)
        search_row.addWidget(self.next_page_button)
        outer.addLayout(search_row)

        dest_row = QHBoxLayout()
        dest_row.addWidget(QLabel("Download folder"))
        self.dest_input = QLineEdit(self._default_download_folder())
        self.dest_browse_button = QPushButton("Browse...")
        self.dest_browse_button.clicked.connect(self._browse_dest_folder)
        dest_row.addWidget(self.dest_input, 1)
        dest_row.addWidget(self.dest_browse_button)
        self.enrich_checkbox = QCheckBox("Auto-enrich comic archives after download")
        self.enrich_checkbox.setChecked(self._auto_enrich_enabled())
        dest_row.addWidget(self.enrich_checkbox)
        outer.addLayout(dest_row)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        results_panel = QWidget()
        results_layout = QVBoxLayout(results_panel)
        results_layout.setContentsMargins(0, 0, SPACING["sm"], 0)
        results_layout.addWidget(QLabel("Results"))
        self.results_list = QListWidget()
        self.results_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.results_list.currentItemChanged.connect(self._on_result_selected)
        results_layout.addWidget(self.results_list, 1)
        splitter.addWidget(results_panel)

        right = QWidget()
        right.setMinimumWidth(400)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(
            SPACING["md"], SPACING["xs"], SPACING["md"], SPACING["md"]
        )
        right_layout.setSpacing(SPACING["md"])

        self.detail_title = QLabel("Select a result to view details")
        self.detail_title.setWordWrap(True)
        right_layout.addWidget(self.detail_title)

        meta_row = QHBoxLayout()
        meta_row.setSpacing(SPACING["md"])
        self.thumbnail_label = QLabel()
        self.thumbnail_label.setFixedSize(120, 180)
        self.thumbnail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        meta_col = QVBoxLayout()
        meta_col.setSpacing(SPACING["sm"])
        meta_col.setContentsMargins(0, SPACING["xs"], 0, 0)
        self.detail_date = QLabel("")
        self.detail_excerpt = QLabel("")
        self.detail_excerpt.setWordWrap(True)
        meta_col.addWidget(self.detail_date)
        meta_col.addWidget(self.detail_excerpt, 1)
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
        action_row.setSpacing(SPACING["sm"])
        self.download_button = QPushButton("Download")
        self.download_button.clicked.connect(lambda: self._start_download())
        self.download_button.setEnabled(False)
        self.browser_button = QPushButton("Open in browser")
        self.browser_button.clicked.connect(self._open_selected_in_browser)
        self.browser_button.setEnabled(False)
        action_row.addWidget(self.download_button)
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
        right_layout.addWidget(self.status_label)

        splitter.addWidget(right)

        wishlist_panel = QWidget()
        wishlist_panel.setMinimumWidth(260)
        wishlist_layout = QVBoxLayout(wishlist_panel)
        wishlist_layout.setContentsMargins(SPACING["sm"], 0, 0, 0)
        wishlist_layout.addWidget(QLabel("Wishlist"))
        self.wishlist_count_label = QLabel("0 items")
        wishlist_layout.addWidget(self.wishlist_count_label)
        self.wishlist_table = QTableWidget(0, 4)
        self.wishlist_table.setHorizontalHeaderLabels(["Series", "Issue", "Volume", "CV Issue"])
        self.wishlist_table.horizontalHeader().setStretchLastSection(True)
        self.wishlist_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.wishlist_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.wishlist_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.wishlist_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.wishlist_table.verticalHeader().setVisible(False)
        wishlist_layout.addWidget(self.wishlist_table, 1)
        primary_wish = QHBoxLayout()
        self.wishlist_download_button = QPushButton("Download")
        self.wishlist_download_button.clicked.connect(self._wishlist_download_selected)
        self.wishlist_download_all_button = QPushButton("Download all")
        self.wishlist_download_all_button.clicked.connect(self._wishlist_download_all)
        primary_wish.addWidget(self.wishlist_download_button)
        primary_wish.addWidget(self.wishlist_download_all_button)
        wishlist_layout.addLayout(primary_wish)
        secondary_wish = QHBoxLayout()
        self.wishlist_search_button = QPushButton("Search")
        self.wishlist_search_button.clicked.connect(self._wishlist_search_selected)
        self.wishlist_remove_button = QPushButton("Remove")
        self.wishlist_remove_button.clicked.connect(self._wishlist_remove_selected)
        self.wishlist_clear_button = QPushButton("Clear")
        self.wishlist_clear_button.clicked.connect(self._wishlist_clear)
        secondary_wish.addWidget(self.wishlist_search_button)
        secondary_wish.addWidget(self.wishlist_remove_button)
        secondary_wish.addWidget(self.wishlist_clear_button)
        wishlist_layout.addLayout(secondary_wish)
        splitter.addWidget(wishlist_panel)

        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        splitter.setStretchFactor(2, 2)
        splitter.setSizes([280, 480, 300])
        outer.addWidget(splitter, 1)
        self.apply_theme(self._theme)

    def apply_theme(self, theme: str) -> None:
        """Re-apply visual tokens for the active theme."""
        self._theme = theme
        c = colors_for(theme)
        self.setStyleSheet(getcomics_panel_stylesheet(theme))
        self.title_label.setStyleSheet(
            f"font-size: 15px; font-weight: 600; color: {c['text']};"
        )
        self.detail_title.setStyleSheet(f"font-weight: 600; color: {c['text']};")
        self.thumbnail_label.setStyleSheet(
            f"background: {c['surface']}; border: 1px solid {c['border']};"
        )
        self.page_label.setStyleSheet(muted_label_stylesheet(theme))
        self.detail_date.setStyleSheet(muted_label_stylesheet(theme))
        self.detail_excerpt.setStyleSheet(f"color: {c['text']};")
        self.status_label.setStyleSheet(muted_label_stylesheet(theme))
        default_btn = button_stylesheet(theme, "default")
        for button in (
            self.search_button,
            self.prev_page_button,
            self.next_page_button,
            self.dest_browse_button,
            self.download_button,
            self.browser_button,
            self.wishlist_search_button,
            self.wishlist_download_button,
            self.wishlist_download_all_button,
            self.wishlist_remove_button,
            self.wishlist_clear_button,
        ):
            button.setStyleSheet(default_btn)

    def set_wishlist_manager(self, manager: WishlistManager | None) -> None:
        self._wishlist_manager = manager
        if manager is not None:
            manager.set_on_changed(self._refresh_wishlist_table)
        self._refresh_wishlist_table()

    def set_download_queue(self, queue: DownloadQueueManager) -> None:
        self._download_queue = queue
        queue.item_updated.connect(self._on_queue_item_updated)

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
        self._pending_excerpt = result.excerpt
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
        excerpt = issue.excerpt or self._pending_excerpt
        if excerpt:
            self.detail_excerpt.setText(excerpt)
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
        if self._download_queue is None:
            QMessageBox.warning(self, "Download queue", "Download queue is not available.")
            return
        dest = self._dest_path()
        if dest is None:
            return
        auto_enrich = self.enrich_checkbox.isChecked()
        if auto_enrich:
            from comicdesk.ui.api_key_prompt import has_api_key, warn_missing_api_key

            if not has_api_key(self.config):
                warn_missing_api_key(
                    self, "Auto-enrich after download from Comic Vine"
                )
                auto_enrich = False
        api_key = self.config.api_key if self.config else ""
        cache_enabled = self.config.cache_enabled if self.config else True
        logger.info(
            "getcomics_action_download issue=%s dest_dir=%s auto_enrich=%s selected_provider=%s",
            self._current_issue.url,
            dest,
            auto_enrich,
            getattr(selected_link, "provider", None),
        )
        item_id = self._download_queue.enqueue(
            self._current_issue,
            dest,
            api_key=api_key,
            cache_enabled=cache_enabled,
            auto_enrich=auto_enrich,
            selected_link=selected_link,
        )
        self._tracked_download_id = item_id
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        message = f"Downloading: {self._current_issue.title}"
        self.status_label.setText(message)
        self.status_message.emit(message)

    def _on_queue_item_updated(self, item_id: str) -> None:
        if self._download_queue is None:
            return
        item = self._download_queue.get_item(item_id)
        if item is None:
            return
        if item.status == DownloadStatus.RUNNING:
            self.progress_bar.setVisible(True)
            self.progress_bar.setValue(item.progress)
            if item.status_message:
                self.status_label.setText(item.status_message)
                self.status_message.emit(item.status_message)
            return
        if item_id != self._tracked_download_id:
            return
        self.progress_bar.setVisible(False)
        if item.status == DownloadStatus.COMPLETED:
            message = item.status_message or f"Saved to {item.result_comic.path if item.result_comic else 'file'}"
            self.status_label.setText(message)
            self.status_message.emit(message)
        elif item.status == DownloadStatus.ERROR:
            self.status_label.setText(item.error_message or item.status_message)
            self.status_message.emit(item.error_message or item.status_message)
            QMessageBox.warning(self, "Download failed", item.error_message or item.status_message)
        elif item.status == DownloadStatus.CANCELLED:
            self.status_label.setText("Download cancelled")
            self.status_message.emit("Download cancelled")
        elif item.status == DownloadStatus.NEEDS_ATTENTION:
            self.status_label.setText("Select a download provider in the Downloads tab")
            self.status_message.emit("Manual provider selection required")
        self._tracked_download_id = None

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
        self._pending_excerpt = ""
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

    def _stop_thumbnail_worker(self):
        worker = self._thumbnail_worker
        if worker is None:
            return
        worker.cancel()
        if worker.isRunning():
            worker.wait(5000)
        worker.deleteLater()
        self._thumbnail_worker = None

    def _refresh_wishlist_table(self) -> None:
        books = self._wishlist_manager.items() if self._wishlist_manager is not None else []
        self.wishlist_table.setRowCount(len(books))
        for row, book in enumerate(books):
            self.wishlist_table.setItem(row, 0, QTableWidgetItem(cbl_book_series_label(book)))
            self.wishlist_table.setItem(row, 1, QTableWidgetItem(cbl_book_issue_label(book)))
            self.wishlist_table.setItem(row, 2, QTableWidgetItem(cbl_book_volume_label(book)))
            self.wishlist_table.setItem(row, 3, QTableWidgetItem(book.cv_issue_id or ""))
            for column in range(4):
                item = self.wishlist_table.item(row, column)
                if item is not None:
                    item.setData(Qt.ItemDataRole.UserRole, book)
        count = len(books)
        label = "1 item" if count == 1 else f"{count} items"
        self.wishlist_count_label.setText(label)
        has_items = count > 0
        self.wishlist_download_all_button.setEnabled(has_items)
        self.wishlist_clear_button.setEnabled(has_items)

    def _selected_wishlist_books(self) -> list[CBLBook]:
        books: list[CBLBook] = []
        seen: set[int] = set()
        for item in self.wishlist_table.selectedItems():
            if item.column() != 0:
                continue
            book = item.data(Qt.ItemDataRole.UserRole)
            if not isinstance(book, CBLBook):
                continue
            book_id = id(book)
            if book_id in seen:
                continue
            seen.add(book_id)
            books.append(book)
        return books

    def _wishlist_search_selected(self) -> None:
        books = self._selected_wishlist_books()
        if not books:
            QMessageBox.information(self, "Wishlist", "Select a wishlist item to search.")
            return
        book = books[0]
        query = build_search_query(book)
        self.query_input.setText(query)
        index = self.criterion_combo.findData("name")
        if index >= 0:
            self.criterion_combo.setCurrentIndex(index)
        self._start_search()

    def _wishlist_download_selected(self) -> None:
        books = self._selected_wishlist_books()
        if not books:
            QMessageBox.information(self, "Wishlist", "Select a wishlist item to download.")
            return
        if len(books) > 1:
            QMessageBox.information(
                self,
                "Wishlist",
                "Select a single wishlist item for individual download.",
            )
            return
        self._resolve_and_enqueue_wishlist_book(books[0])

    def _wishlist_download_all(self) -> None:
        if self._wishlist_manager is None:
            return
        books = self._wishlist_manager.items()
        if not books:
            return
        if self._download_queue is None:
            QMessageBox.warning(self, "Download queue", "Download queue is not available.")
            return
        dest = self._dest_path()
        if dest is None:
            return
        answer = QMessageBox.question(
            self,
            "Download all",
            f"Resolve and queue downloads for {len(books)} wishlist item(s)?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._stop_wishlist_batch_worker()
        self._wishlist_batch_worker = WishlistBatchDownloadWorker(books)
        worker = self._wishlist_batch_worker
        worker.progress.connect(self._on_wishlist_batch_progress)
        worker.item_finished.connect(self._on_wishlist_batch_item_finished)
        worker.item_error.connect(self._on_wishlist_batch_item_error)
        worker.finished.connect(self._on_wishlist_batch_finished)
        worker.start()
        self._set_wishlist_busy(True, f"Resolving 0/{len(books)} wishlist items...")

    def _resolve_and_enqueue_wishlist_book(self, book: CBLBook) -> None:
        if self._download_queue is None:
            QMessageBox.warning(self, "Download queue", "Download queue is not available.")
            return
        dest = self._dest_path()
        if dest is None:
            return
        self._stop_wishlist_worker()
        self._wishlist_worker = WishlistDownloadWorker(book)
        worker = self._wishlist_worker
        worker.finished.connect(self._on_wishlist_download_finished)
        worker.error.connect(self._on_wishlist_download_error)
        worker.start()
        self._set_wishlist_busy(True, f"Resolving: {book.series_name} #{book.issue_number}")

    def _enqueue_wishlist_issue(self, book: CBLBook, issue: GetComicsIssue) -> None:
        if self._download_queue is None:
            return
        dest = self._dest_path()
        if dest is None:
            return
        auto_enrich = self.enrich_checkbox.isChecked()
        if auto_enrich:
            from comicdesk.ui.api_key_prompt import has_api_key, warn_missing_api_key

            if not has_api_key(self.config):
                warn_missing_api_key(
                    self, "Auto-enrich after download from Comic Vine"
                )
                auto_enrich = False
        api_key = self.config.api_key if self.config else ""
        cache_enabled = self.config.cache_enabled if self.config else True
        item_id = self._download_queue.enqueue(
            issue,
            dest,
            api_key=api_key,
            cache_enabled=cache_enabled,
            auto_enrich=auto_enrich,
        )
        self._tracked_download_id = item_id
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        message = f"Queued download: {issue.title}"
        self.status_label.setText(message)
        self.status_message.emit(message)

    def _on_wishlist_download_finished(self, book: CBLBook, issue: GetComicsIssue) -> None:
        if self._wishlist_worker is None:
            return
        self._set_wishlist_busy(False)
        self._current_issue = issue
        self.detail_title.setText(issue.title)
        self.detail_date.setText(issue.date)
        self.detail_excerpt.setText(issue.excerpt)
        self._populate_links_table(issue.download_links)
        self.download_button.setEnabled(True)
        self.browser_button.setEnabled(True)
        self._enqueue_wishlist_issue(book, issue)

    def _on_wishlist_download_error(self, book: CBLBook, message: str) -> None:
        if self._wishlist_worker is None:
            return
        self._set_wishlist_busy(False)
        self.status_label.setText(message)
        self.status_message.emit(message)
        answer = QMessageBox.question(
            self,
            "Wishlist download",
            f"{message}\n\nSearch manually for this item?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.wishlist_table.selectRow(self._wishlist_row_for_book(book))
            self._wishlist_search_selected()

    def _wishlist_row_for_book(self, book: CBLBook) -> int:
        for row in range(self.wishlist_table.rowCount()):
            item = self.wishlist_table.item(row, 0)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) is book:
                return row
        return 0

    def _on_wishlist_batch_progress(self, current: int, total: int, book: CBLBook) -> None:
        label = f"{book.series_name} #{book.issue_number}".strip()
        self._set_wishlist_busy(True, f"Resolving {current}/{total}: {label}")

    def _on_wishlist_batch_item_finished(self, book: CBLBook, issue: GetComicsIssue) -> None:
        self._enqueue_wishlist_issue(book, issue)

    def _on_wishlist_batch_item_error(self, book: CBLBook, message: str) -> None:
        logger.warning(
            "wishlist_batch_item_failed series=%s issue=%s error=%s",
            book.series_name,
            book.issue_number,
            message,
        )

    def _on_wishlist_batch_finished(self, resolved: int, failed: int) -> None:
        self._set_wishlist_busy(False)
        message = f"Wishlist batch: {resolved} queued, {failed} failed"
        self.status_label.setText(message)
        self.status_message.emit(message)
        if failed:
            QMessageBox.information(self, "Wishlist download", message)

    def _wishlist_remove_selected(self) -> None:
        if self._wishlist_manager is None:
            return
        books = self._selected_wishlist_books()
        if not books:
            QMessageBox.information(self, "Wishlist", "Select wishlist item(s) to remove.")
            return
        removed = self._wishlist_manager.remove_books(books)
        if removed:
            self.status_message.emit(f"Removed {removed} wishlist item(s)")

    def _wishlist_clear(self) -> None:
        if self._wishlist_manager is None or not self._wishlist_manager.items():
            return
        answer = QMessageBox.question(
            self,
            "Clear wishlist",
            "Remove all wishlist items?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._wishlist_manager.clear()
        self.status_message.emit("Wishlist cleared")

    def _set_wishlist_busy(self, busy: bool, message: str = "") -> None:
        for button in (
            self.wishlist_search_button,
            self.wishlist_download_button,
            self.wishlist_download_all_button,
            self.wishlist_remove_button,
            self.wishlist_clear_button,
        ):
            button.setEnabled(not busy)
        if not busy:
            self._refresh_wishlist_table()
        if message:
            self.status_label.setText(message)
            self.status_message.emit(message)

    def _stop_wishlist_worker(self) -> None:
        worker = self._wishlist_worker
        if worker is None:
            return
        worker.cancel()
        if worker.isRunning():
            worker.wait(5000)
        worker.deleteLater()
        self._wishlist_worker = None

    def _stop_wishlist_batch_worker(self) -> None:
        worker = self._wishlist_batch_worker
        if worker is None:
            return
        worker.cancel()
        if worker.isRunning():
            worker.wait(5000)
        worker.deleteLater()
        self._wishlist_batch_worker = None

    def shutdown_workers(self):
        logger.info("getcomics_action_shutdown_workers")
        self._stop_search_worker()
        self._stop_issue_worker()
        self._stop_thumbnail_worker()
        self._stop_wishlist_worker()
        self._stop_wishlist_batch_worker()
