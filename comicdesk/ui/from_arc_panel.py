"""Import a Comic Vine story arc into the CBL editor."""

from __future__ import annotations

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
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
from comicdesk.models import Comic, ComicVineStoryArc
from comicdesk.services.arc_list_import import ArcReadingListItem, match_arc_items_to_library
from comicdesk.services.comicvine_api import ComicVineClient, ComicVineError
from comicdesk.ui.theme import button_stylesheet, muted_label_stylesheet


class _StoryArcSearchWorker(QThread):
    finished = Signal(list)
    error = Signal(str)

    def __init__(self, config: Config, query: str):
        super().__init__()
        self.config = config
        self.query = query

    def run(self):
        api_key = str(self.config.api_key or "").strip()
        if not api_key:
            self.error.emit("Set a Comic Vine API key in Settings.")
            return
        client = ComicVineClient(api_key, cache_enabled=self.config.cache_enabled)
        try:
            arcs = client.search_story_arcs(self.query)
            self.finished.emit(arcs)
        except ComicVineError as exc:
            self.error.emit(str(exc))


class _StoryArcImportWorker(QThread):
    finished = Signal(list)
    error = Signal(str)

    def __init__(self, config: Config, arc_id: str):
        super().__init__()
        self.config = config
        self.arc_id = arc_id

    def run(self):
        api_key = str(self.config.api_key or "").strip()
        if not api_key:
            self.error.emit("Set a Comic Vine API key in Settings.")
            return
        client = ComicVineClient(api_key, cache_enabled=self.config.cache_enabled)
        try:
            items = client.story_arc_issue_items(self.arc_id)
            self.finished.emit(items)
        except ComicVineError as exc:
            self.error.emit(str(exc))


class FromArcPanel(QWidget):
    """Search Comic Vine story arcs and merge issues into the active CBL."""

    import_requested = Signal(list)
    status_message = Signal(str)

    def __init__(self, config: Config | None = None, parent=None):
        super().__init__(parent)
        self.config = config
        self._theme = "dark"
        self._comics: list[Comic] = []
        self._search_worker: _StoryArcSearchWorker | None = None
        self._import_worker: _StoryArcImportWorker | None = None
        self._search_busy = False
        self._import_busy = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        hint = QLabel(
            "Search Comic Vine story arcs, then import their issues in Comic Vine order. "
            "Local files are matched by Comic Vine issue ID when possible."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        row = QHBoxLayout()
        self.query_input = QLineEdit()
        self.query_input.setPlaceholderText("Story arc name…")
        self.query_input.returnPressed.connect(self._search_arcs)
        self.search_btn = QPushButton("Search Comic Vine")
        self.search_btn.clicked.connect(self._search_arcs)
        row.addWidget(self.query_input, 1)
        row.addWidget(self.search_btn)
        layout.addLayout(row)
        self.search_progress = QProgressBar()
        self.search_progress.setRange(0, 0)
        self.search_progress.setFixedHeight(6)
        self.search_progress.setTextVisible(False)
        self.search_progress.hide()
        layout.addWidget(self.search_progress)
        self.results_list = QListWidget()
        self.results_list.currentItemChanged.connect(self._update_import_enabled)
        layout.addWidget(self.results_list, 1)
        self.import_btn = QPushButton("Import into list")
        self.import_btn.clicked.connect(self._import_selected)
        self.import_btn.setEnabled(False)
        layout.addWidget(self.import_btn)
        self.import_progress = QProgressBar()
        self.import_progress.setRange(0, 0)
        self.import_progress.setFixedHeight(6)
        self.import_progress.setTextVisible(False)
        self.import_progress.hide()
        layout.addWidget(self.import_progress)
        self.status_label = QLabel("Requires a Comic Vine API key in Settings.")
        layout.addWidget(self.status_label)
        self.apply_theme(self._theme)

    def set_config(self, config: Config) -> None:
        self.config = config

    def set_comics(self, comics: list[Comic]) -> None:
        self._comics = list(comics)

    def _update_import_enabled(self, *_args) -> None:
        can_import = (
            not self._import_busy
            and not self._search_busy
            and self.results_list.currentItem() is not None
        )
        self.import_btn.setEnabled(can_import)

    def _set_search_busy(self, busy: bool) -> None:
        self._search_busy = busy
        self.search_btn.setEnabled(not busy)
        self.query_input.setEnabled(not busy)
        self.search_progress.setVisible(busy)
        self._update_import_enabled()

    def _set_import_busy(self, busy: bool) -> None:
        self._import_busy = busy
        self.import_progress.setVisible(busy)
        self.results_list.setEnabled(not busy)
        self._update_import_enabled()

    def _search_arcs(self) -> None:
        if self.config is None or self._search_busy:
            return
        query = self.query_input.text().strip()
        if not query:
            return
        self._set_search_busy(True)
        self.status_label.setText("Searching story arcs on Comic Vine…")
        self._search_worker = _StoryArcSearchWorker(self.config, query)
        worker = self._search_worker
        worker.finished.connect(self._on_arcs)
        worker.error.connect(self._on_search_error)
        worker.start()

    def _on_arcs(self, arcs: list) -> None:
        self._set_search_busy(False)
        self.results_list.clear()
        for entry in arcs:
            if not isinstance(entry, ComicVineStoryArc):
                continue
            label = entry.name
            if entry.deck:
                label = f"{entry.name} — {entry.deck}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, entry.id)
            self.results_list.addItem(item)
        if arcs:
            self.results_list.setCurrentRow(0)
            self.status_label.setText(f"{len(arcs)} story arc(s) found. Select one and import.")
        else:
            self.status_label.setText(
                "No story arcs matched. Try a shorter phrase (e.g. “under doom”) "
                "or check spelling (“world” vs “word”)."
            )
        self._update_import_enabled()

    def _on_search_error(self, message: str) -> None:
        self._set_search_busy(False)
        self.status_label.setText(message)
        QMessageBox.warning(self, "Comic Vine", message)

    def _import_selected(self) -> None:
        if self.config is None or self._import_busy or self._search_busy:
            return
        item = self.results_list.currentItem()
        if item is None:
            QMessageBox.information(self, "From arc", "Select a story arc first.")
            return
        arc_id = item.data(Qt.ItemDataRole.UserRole)
        if not arc_id:
            return
        self._set_import_busy(True)
        self.status_label.setText("Loading arc issues from Comic Vine…")
        self._import_worker = _StoryArcImportWorker(self.config, str(arc_id))
        worker = self._import_worker
        worker.finished.connect(self._on_import_items)
        worker.error.connect(self._on_import_error)
        worker.start()

    def _on_import_error(self, message: str) -> None:
        self._set_import_busy(False)
        self.status_label.setText(message)
        QMessageBox.warning(self, "Comic Vine", message)

    def _on_import_items(self, items: list) -> None:
        self._set_import_busy(False)
        if not items:
            QMessageBox.information(
                self,
                "From arc",
                "Comic Vine returned no issues for this story arc.",
            )
            self.status_label.setText("No issues in this arc.")
            return
        typed = [entry for entry in items if isinstance(entry, ArcReadingListItem)]
        ordered, linked, missing = match_arc_items_to_library(typed, self._comics)
        self.import_requested.emit(ordered)
        self.status_message.emit(
            f"Imported arc list: {linked} linked, {missing} without local files"
        )
        self.status_label.setText(
            f"Imported {len(ordered)} entries ({linked} on disk, {missing} virtual)."
        )

    def apply_theme(self, theme: str) -> None:
        self._theme = theme
        self.status_label.setStyleSheet(muted_label_stylesheet(theme))
        default = button_stylesheet(theme, "default")
        self.search_btn.setStyleSheet(default)
        self.import_btn.setStyleSheet(default)
