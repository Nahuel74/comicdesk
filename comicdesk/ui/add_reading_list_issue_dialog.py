"""Dialog to add a virtual issue to the active reading list."""

from __future__ import annotations

import logging
from pathlib import Path

import httpx
from PySide6.QtCore import QSize, Qt, QThread, Signal
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
    QWidget,
)

from comicdesk.config import Config
from comicdesk.models import Comic, ComicVineIssue, ComicVineVolume
from comicdesk.ui.cbz_metadata_workers import MetadataSearchWorker
from comicdesk.ui.theme import dialog_stylesheet, muted_label_stylesheet

logger = logging.getLogger(__name__)

_COVER_WIDTH = 52
_COVER_HEIGHT = 78
_ROW_HEIGHT = 88


class _CoverLoader(QThread):
    finished = Signal(bytes, int)
    error = Signal(int)

    def __init__(self, url: str, row: int):
        super().__init__()
        self.url = url
        self.row = row
        self._cancelled = False

    def run(self) -> None:
        if self._cancelled or not self.url:
            return
        try:
            response = httpx.get(
                self.url,
                timeout=20,
                follow_redirects=True,
                headers={"User-Agent": "ComicDesk/1.0"},
            )
            response.raise_for_status()
            if not self._cancelled:
                self.finished.emit(response.content, self.row)
        except Exception:
            logger.debug("cover_load_failed url=%s", self.url, exc_info=True)
            if not self._cancelled:
                self.error.emit(self.row)

    def cancel(self) -> None:
        self._cancelled = True


class _CandidateResultRow(QWidget):
    """One search hit with cover art and descriptive text."""

    def __init__(self, headline: str, subtitle: str, detail: str, theme: str, parent=None):
        super().__init__(parent)
        self._theme = theme
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(10)
        self.cover_label = QLabel("…")
        self.cover_label.setFixedSize(_COVER_WIDTH, _COVER_HEIGHT)
        self.cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover_label.setStyleSheet(muted_label_stylesheet(theme))
        layout.addWidget(self.cover_label)
        text_column = QVBoxLayout()
        text_column.setSpacing(2)
        self.headline_label = QLabel(headline)
        self.headline_label.setWordWrap(True)
        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setWordWrap(True)
        self.subtitle_label.setStyleSheet(muted_label_stylesheet(theme))
        self.detail_label = QLabel(detail)
        self.detail_label.setWordWrap(True)
        self.detail_label.setStyleSheet(muted_label_stylesheet(theme))
        text_column.addWidget(self.headline_label)
        text_column.addWidget(self.subtitle_label)
        text_column.addWidget(self.detail_label)
        text_column.addStretch()
        layout.addLayout(text_column, 1)

    def set_cover_pixmap(self, pixmap: QPixmap) -> None:
        scaled = pixmap.scaled(
            self.cover_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.cover_label.setPixmap(scaled)
        self.cover_label.setText("")

    def set_cover_failed(self) -> None:
        self.cover_label.setText("—")
        self.cover_label.setPixmap(QPixmap())


class AddReadingListIssueDialog(QDialog):
    """Collect metadata for a list entry without a local CBZ file."""

    def __init__(self, config: Config, parent=None):
        super().__init__(parent)
        self.config = config
        self._search_worker: MetadataSearchWorker | None = None
        self._cover_loaders: list[_CoverLoader] = []
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
        self.results_list.setIconSize(QSize(_COVER_WIDTH, _COVER_HEIGHT))
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

    def _stop_cover_loaders(self) -> None:
        for loader in self._cover_loaders:
            loader.cancel()
            if loader.isRunning():
                loader.wait(100)
            loader.deleteLater()
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
        if not candidates:
            volumes = list(getattr(result, "volumes", []) or [])
            candidates = volumes
        self.results_list.clear()
        for row, candidate in enumerate(candidates):
            headline, subtitle, detail = self._candidate_lines(candidate)
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, candidate)
            item.setSizeHint(QSize(0, _ROW_HEIGHT))
            row_widget = _CandidateResultRow(headline, subtitle, detail, self._theme)
            self.results_list.addItem(item)
            self.results_list.setItemWidget(item, row_widget)
            image_url = getattr(candidate, "image_url", "") or ""
            if image_url:
                loader = _CoverLoader(image_url, row)
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

    def _on_cover_loaded(self, data: bytes, row: int, worker: _CoverLoader) -> None:
        if worker in self._cover_loaders:
            self._cover_loaders.remove(worker)
        worker.deleteLater()
        if row < 0 or row >= self.results_list.count():
            return
        item = self.results_list.item(row)
        widget = self.results_list.itemWidget(item)
        if not isinstance(widget, _CandidateResultRow):
            return
        pixmap = QPixmap()
        if pixmap.loadFromData(data):
            widget.set_cover_pixmap(pixmap)

    def _on_cover_error(self, row: int, worker: _CoverLoader) -> None:
        if worker in self._cover_loaders:
            self._cover_loaders.remove(worker)
        worker.deleteLater()
        if row < 0 or row >= self.results_list.count():
            return
        item = self.results_list.item(row)
        widget = self.results_list.itemWidget(item)
        if isinstance(widget, _CandidateResultRow):
            widget.set_cover_failed()

    def _search_error(self, message: str, worker) -> None:
        if worker is not self._search_worker:
            return
        self._search_worker = None
        worker.deleteLater()
        self._set_search_busy(False)
        self.results_label.setText(message)

    @staticmethod
    def _release_label(issue: ComicVineIssue) -> str:
        store = (issue.store_date or "").strip()
        if store:
            return f"Released: {store[:10]}"
        return ""

    @classmethod
    def _candidate_lines(cls, candidate) -> tuple[str, str, str]:
        if isinstance(candidate, ComicVineIssue):
            series = candidate.series_name or "Unknown series"
            number = candidate.issue_number or "?"
            headline = f"{series} #{number}"
            subtitle = (candidate.name or "").strip() or "—"
            detail = cls._release_label(candidate)
            if not detail:
                year = candidate.volume_start_year or ""
                if year:
                    detail = f"Series started: {year}"
            return headline, subtitle, detail
        if isinstance(candidate, ComicVineVolume):
            headline = candidate.name or "Unknown series"
            subtitle = "Series / volume"
            year = candidate.start_year or ""
            detail = f"Started: {year}" if year else ""
            return headline, subtitle, detail
        name = getattr(candidate, "name", "") or getattr(candidate, "series_name", "")
        return name or "Result", "", ""

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
