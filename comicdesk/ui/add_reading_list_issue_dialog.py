"""Dialog to add a virtual issue to the active reading list."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from comicdesk.config import Config
from comicdesk.models import Comic, ComicVineIssue, ComicVineVolume
from comicdesk.ui.cbz_metadata_workers import MetadataSearchWorker
from comicdesk.ui.comicvine_candidate_widgets import (
    CANDIDATE_ROW_HEIGHT,
    COVER_HEIGHT,
    COVER_WIDTH,
    CandidateResultRow,
    CoverLoader,
    candidate_lines,
)
from comicdesk.ui.theme import dialog_stylesheet

logger = logging.getLogger(__name__)

WORKER_JOIN_TIMEOUT_MS = 5000


class AddReadingListIssueDialog(QDialog):
    """Collect metadata for a list entry without a local CBZ file."""

    def __init__(self, config: Config, parent=None):
        super().__init__(parent)
        self.config = config
        self._search_worker: MetadataSearchWorker | None = None
        self._cover_loaders: list[CoverLoader] = []
        self._issue_title = ""
        self._theme = "dark"
        self._form_fields: list[QLineEdit] = []
        self.setWindowTitle("Add issue")
        self.setMinimumWidth(480)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.series_edit = QLineEdit()
        self.issue_edit = QLineEdit()
        self.volume_edit = QLineEdit()
        self.year_edit = QLineEdit()
        self.cv_series_edit = QLineEdit()
        self.cv_issue_edit = QLineEdit()
        form.addRow("Series", self.series_edit)
        form.addRow("Issue number", self.issue_edit)
        form.addRow("Volume", self.volume_edit)
        form.addRow("Year", self.year_edit)
        form.addRow("Series ID", self.cv_series_edit)
        form.addRow("Issue ID", self.cv_issue_edit)
        layout.addLayout(form)
        self._form_fields = [
            self.series_edit,
            self.issue_edit,
            self.volume_edit,
            self.year_edit,
            self.cv_series_edit,
            self.cv_issue_edit,
        ]
        for field in self._form_fields:
            field.returnPressed.connect(self._start_search)

        search_row = QHBoxLayout()
        self.search_btn = QPushButton("Search metadata")
        self.search_btn.clicked.connect(self._start_search)
        self.search_progress = QProgressBar()
        self.search_progress.setRange(0, 0)
        self.search_progress.setFixedHeight(8)
        self.search_progress.setTextVisible(False)
        self.search_progress.hide()
        search_row.addWidget(self.search_btn)
        search_row.addWidget(self.search_progress, 1)
        layout.addLayout(search_row)

        self.results_label = QLabel("")
        layout.addWidget(self.results_label)
        self.results_list = QListWidget()
        self.results_list.setMinimumHeight(200)
        self.results_list.setIconSize(QSize(COVER_WIDTH, COVER_HEIGHT))
        self.results_list.itemDoubleClicked.connect(self._apply_candidate)
        layout.addWidget(self.results_list)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.button_box.accepted.connect(self._accept)
        self.button_box.rejected.connect(self.reject)
        ok_button = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
        cancel_button = self.button_box.button(QDialogButtonBox.StandardButton.Cancel)
        if ok_button is not None:
            ok_button.setAutoDefault(False)
            ok_button.setDefault(False)
        if cancel_button is not None:
            cancel_button.setAutoDefault(False)
        self.search_btn.setAutoDefault(True)
        self.search_btn.setDefault(True)
        layout.addWidget(self.button_box)

        api_key = str(getattr(self.config, "api_key", "") or "").strip()
        self._api_key_configured = bool(api_key)
        self.search_btn.setEnabled(self._api_key_configured)

    def apply_theme(self, theme: str) -> None:
        self._theme = theme
        self.setStyleSheet(dialog_stylesheet(theme))

    def built_comic(self) -> Comic | None:
        series = self.series_edit.text().strip()
        issue = self.issue_edit.text().strip()
        cv_issue = self.cv_issue_edit.text().strip() or None
        if not series and not issue and not cv_issue:
            return None
        if not ((series and issue) or cv_issue):
            return None
        return Comic(
            path=Path(),
            title=self._issue_title,
            series_name=series,
            issue_number=issue,
            volume=self.volume_edit.text().strip(),
            year=self.year_edit.text().strip(),
            cv_series_id=self.cv_series_edit.text().strip() or None,
            cv_issue_id=cv_issue,
        )

    def _accept(self) -> None:
        if self.built_comic() is None:
            QMessageBox.warning(
                self,
                "Add issue",
                "Enter series and issue number, or an issue ID from metadata search.",
            )
            return
        self.accept()

    def _set_search_busy(self, busy: bool) -> None:
        self.search_progress.setVisible(busy)
        self.search_btn.setEnabled(not busy and self._api_key_configured)
        for field in self._form_fields:
            field.setEnabled(not busy)
        self.results_list.setEnabled(not busy)
        ok_button = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
        if ok_button is not None:
            ok_button.setEnabled(not busy)
        if busy:
            self.results_label.setText("Searching…")

    def _join_or_defer_delete(self, thread, *, defer_signals=None) -> None:
        if thread.isRunning():
            if not thread.wait(WORKER_JOIN_TIMEOUT_MS):
                signals = defer_signals if defer_signals is not None else (thread.finished,)
                for signal in signals:
                    signal.connect(thread.deleteLater)
                return
        thread.deleteLater()

    def _release_cover_loader(self, loader: CoverLoader) -> None:
        if loader in self._cover_loaders:
            self._cover_loaders.remove(loader)
        loader.cancel()
        try:
            loader.finished.disconnect()
        except (TypeError, RuntimeError):
            pass
        try:
            loader.error.disconnect()
        except (TypeError, RuntimeError):
            pass
        self._join_or_defer_delete(
            loader, defer_signals=(loader.finished, loader.error)
        )

    def _stop_cover_loaders(self) -> None:
        for loader in list(self._cover_loaders):
            self._release_cover_loader(loader)
        self._cover_loaders.clear()

    def _start_search(self) -> None:
        from comicdesk.ui.api_key_prompt import ensure_api_key

        if not ensure_api_key(self, self.config, "Metadata search"):
            return
        if self._search_worker is not None:
            return
        self._stop_cover_loaders()
        draft = Comic(
            path=Path(),
            series_name=self.series_edit.text().strip(),
            issue_number=self.issue_edit.text().strip(),
            volume=self.volume_edit.text().strip(),
            year=self.year_edit.text().strip(),
        )
        key = str(self.config.api_key or "").strip()
        self._set_search_busy(True)
        self.results_list.clear()
        self._search_worker = MetadataSearchWorker(
            draft,
            key,
            cache_enabled=bool(getattr(self.config, "cache_enabled", True)),
        )
        worker = self._search_worker
        worker.finished.connect(lambda result, w=worker: self._search_finished(result, w))
        worker.error.connect(lambda message, w=worker: self._search_error(message, w))
        worker.start()

    def _search_finished(self, result, worker) -> None:
        if worker is not self._search_worker:
            return
        self._search_worker = None
        worker.deleteLater()
        self._set_search_busy(False)
        candidates: list = list(getattr(result, "issues", []) or [])
        if not candidates and getattr(result, "issue", None) is not None:
            candidates = [result.issue]
        self.results_list.clear()
        for row, candidate in enumerate(candidates):
            headline, subtitle, detail = candidate_lines(candidate)
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, candidate)
            item.setSizeHint(QSize(0, CANDIDATE_ROW_HEIGHT))
            row_widget = CandidateResultRow(headline, subtitle, detail, self._theme)
            self.results_list.addItem(item)
            self.results_list.setItemWidget(item, row_widget)
            image_url = getattr(candidate, "image_url", "") or ""
            if image_url:
                loader = CoverLoader(image_url, row)
                loader.finished.connect(
                    lambda data, r, w=loader: self._on_cover_loaded(data, r, w)
                )
                loader.error.connect(lambda r, w=loader: self._on_cover_error(r, w))
                self._cover_loaders.append(loader)
                loader.start()
        count = len(candidates)
        self.results_label.setText(
            f"{count} result{'s' if count != 1 else ''}" if count else "No results"
        )

    def _on_cover_loaded(self, data: bytes, row: int, worker: CoverLoader) -> None:
        if worker in self._cover_loaders:
            self._cover_loaders.remove(worker)
        worker.deleteLater()
        if row < 0 or row >= self.results_list.count():
            return
        item = self.results_list.item(row)
        widget = self.results_list.itemWidget(item)
        if not isinstance(widget, CandidateResultRow):
            return
        pixmap = QPixmap()
        if pixmap.loadFromData(data):
            widget.set_cover_pixmap(pixmap)

    def _on_cover_error(self, row: int, worker: CoverLoader) -> None:
        if worker in self._cover_loaders:
            self._cover_loaders.remove(worker)
        worker.deleteLater()
        if row < 0 or row >= self.results_list.count():
            return
        item = self.results_list.item(row)
        widget = self.results_list.itemWidget(item)
        if isinstance(widget, CandidateResultRow):
            widget.set_cover_failed()

    def _search_error(self, message: str, worker) -> None:
        if worker is not self._search_worker:
            return
        self._search_worker = None
        worker.deleteLater()
        self._set_search_busy(False)
        self.results_label.setText(message)

    def _apply_candidate(self, item: QListWidgetItem | None = None) -> None:
        if item is None:
            item = self.results_list.currentItem()
        if item is None:
            return
        candidate = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(candidate, ComicVineIssue):
            self._issue_title = (candidate.name or "").strip()
            self.series_edit.setText(candidate.series_name or candidate.name or "")
            self.issue_edit.setText(candidate.issue_number or "")
            volume_year = candidate.volume_start_year or candidate.volume or ""
            self.volume_edit.setText(volume_year)
            store = (candidate.store_date or "").strip()
            if store and len(store) >= 4:
                self.year_edit.setText(store[:4])
            elif volume_year:
                self.year_edit.setText(volume_year[:4] if len(volume_year) >= 4 else volume_year)
            self.cv_series_edit.setText(candidate.series_id or "")
            self.cv_issue_edit.setText(candidate.id or "")
        elif isinstance(candidate, ComicVineVolume):
            self._issue_title = ""
            self.series_edit.setText(candidate.name or "")
            self.volume_edit.setText(candidate.start_year or "")
            self.year_edit.setText(candidate.start_year or "")
            self.cv_series_edit.setText(candidate.id or "")

    def reject(self) -> None:
        if self._search_worker is not None:
            self._search_worker.cancel()
        self._stop_cover_loaders()
        super().reject()
