"""Comic list panel with search, filtering and Comic Vine enrichment."""

from pathlib import Path

from PySide6.QtCore import QItemSelection, QItemSelectionModel, Signal, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView, QHeaderView, QLabel, QMenu, QPushButton, QTableView,
    QHBoxLayout, QMessageBox,
    QVBoxLayout, QWidget,
)

from comicdesk.models import Comic
from comicdesk.ui.comic_list_toolbar import ComicListToolbar
from comicdesk.ui.comic_list_workers import EnrichWorker as _EnrichWorker, ScanWorker
from comicdesk.ui.comic_table_model import ComicFilterProxyModel, ComicTableModel
from comicdesk.ui.comic_selection import ComicSelection
from comicdesk.services.comicvine_api import ComicVineClient
from comicdesk.ui.theme import button_stylesheet, muted_label_stylesheet, table_stylesheet
from comicdesk.ui.widgets.responsive_action_bar import ResponsiveActionBar


class EnrichWorker(_EnrichWorker):
    """Compatibility export retaining the historical patch point."""

    def run(self):
        from comicdesk.ui import comic_list_workers
        factory = comic_list_workers.ComicVineClient
        comic_list_workers.ComicVineClient = ComicVineClient
        try:
            return super().run()
        finally:
            comic_list_workers.ComicVineClient = factory


class ComicListTable(QTableView):
    """Table view configured for comic rows."""

    def __init__(self, source_model=None, parent=None):
        super().__init__(parent)
        # Do not use truthiness here: wrapped Qt objects can evaluate false even
        # when they are valid models (notably while a model is being reset).
        self.source_model = source_model if source_model is not None else ComicTableModel(self)
        self.proxy_model = ComicFilterProxyModel(self)
        self.proxy_model.setSourceModel(self.source_model)
        super().setModel(self.proxy_model)
        header = self.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        for col in range(2, 6):
            header.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setTextElideMode(Qt.ElideRight)
        self.setToolTipDuration(5000)


class ComicList(QWidget):
    """Panel displaying scanned comics without mutating the source list on filter."""

    comics_selected = Signal(list)
    comic_focused = Signal(object)
    comic_edit_requested = Signal(object)
    comics_changed = Signal(list)
    scan_completed = Signal(list)

    def __init__(self, config=None):
        super().__init__()
        self.comics = []
        self.current_folder = None
        self.reading_list = None
        self._selection = ComicSelection()
        self.config = config
        self._theme = "dark"
        self.model = ComicTableModel(parent=self)
        self.table = ComicListTable(self.model, self)
        self.toolbar = ComicListToolbar(self)
        self._setup_ui()
        self.toolbar.query_changed.connect(self.table.proxy_model.set_query)
        self.toolbar.status_changed.connect(self.table.proxy_model.set_status)
        self.table.selectionModel().selectionChanged.connect(self._update_counts)
        self.table.selectionModel().currentChanged.connect(lambda *_: self._emit_focus())
        self.table.doubleClicked.connect(self._request_edit)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        actions_row = QWidget()
        actions_layout = QHBoxLayout(actions_row)
        actions_layout.setContentsMargins(12, 8, 12, 8)
        self.action_bar = ResponsiveActionBar()
        self.enrich_btn = QPushButton("Enrich all metadata")
        self.enrich_btn.setProperty("primary", True)
        self.enrich_btn.setToolTip(
            "Fetch and save external metadata for every comic in this folder"
        )
        self.enrich_btn.clicked.connect(self._on_enrich)
        self.add_selected_btn = QPushButton("Add to list")
        self.add_selected_btn.setToolTip("Add the selected comics to the reading list")
        self.add_selected_btn.setEnabled(False)
        self.add_selected_btn.clicked.connect(self._add_to_list)
        self.clear_selection_btn = QPushButton("Clear selection")
        self.clear_selection_btn.setToolTip("Clear the current comic selection")
        self.clear_selection_btn.setEnabled(False)
        self.clear_selection_btn.clicked.connect(self._clear_selection)
        self.action_bar.add_action(self.enrich_btn, "Enrich all metadata")
        self.action_bar.add_action(self.add_selected_btn, "Add to reading list")
        self.action_bar.add_action(self.clear_selection_btn, "Clear selection")
        actions_layout.addWidget(self.action_bar, 1)
        layout.addWidget(actions_row)
        layout.addWidget(self.toolbar)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        layout.addWidget(self.table)
        self.status_label = QLabel("No comics loaded")
        layout.addWidget(self.status_label)
        self.apply_theme(self._theme)

    def apply_theme(self, theme: str) -> None:
        """Re-apply visual tokens for the active theme."""
        self._theme = theme
        self.enrich_btn.setStyleSheet(button_stylesheet(theme, "primary"))
        self.table.setStyleSheet(table_stylesheet(theme))
        self.status_label.setStyleSheet(
            muted_label_stylesheet(theme) + " padding: 8px 12px;"
        )
        self.toolbar.apply_theme(theme)
        self.action_bar.apply_theme(theme)

    def load_folder(self, path: Path):
        self.current_folder = path
        self._stop_scan_worker()
        self.status_label.setText("Scanning...")
        self.worker = ScanWorker(path)
        worker = self.worker
        self._scan_finished_handler = lambda comics: self._on_scan_complete(comics, worker)
        self._scan_progress_handler = lambda name: self._on_scan_progress(name, worker)
        worker.finished.connect(self._scan_finished_handler)
        worker.progress.connect(self._scan_progress_handler)
        worker.error.connect(lambda message, w=worker: self._on_scan_error(message, w))
        worker.start()

    def _stop_scan_worker(self):
        """Cancel and reap a previous scan before starting another one."""
        worker = getattr(self, "worker", None)
        if worker is None:
            return
        worker.cancel()
        if worker.isRunning():
            worker.wait()
        handler = getattr(self, "_scan_finished_handler", None)
        if handler is not None:
            try:
                worker.finished.disconnect(handler)
            except (RuntimeError, TypeError):
                pass
        progress_handler = getattr(self, "_scan_progress_handler", None)
        if progress_handler is not None:
            try:
                worker.progress.disconnect(progress_handler)
            except (RuntimeError, TypeError):
                pass
        worker.deleteLater()
        self.worker = None
        self._scan_finished_handler = None
        self._scan_progress_handler = None

    def _stop_enrich_worker(self):
        """Cancel and reap an enrichment worker during window shutdown."""
        worker = getattr(self, "enrich_worker", None)
        if worker is None:
            return
        worker.cancel()
        if worker.isRunning():
            worker.wait()
        worker.deleteLater()
        self.enrich_worker = None

    def shutdown_workers(self):
        """Synchronously stop every worker owned by this panel."""
        self._stop_scan_worker()
        self._stop_enrich_worker()

    def _on_scan_progress(self, name, worker):
        if worker is self.worker:
            self.status_label.setText(f"Scanning: {name}")

    def _on_scan_complete(self, comics: list[Comic], worker=None):
        if worker is not None and worker is not self.worker:
            return
        self.comics = comics
        self._set_comics(comics)
        self.set_reading_list(self.reading_list)
        self.status_label.setText(f"Found {len(comics)} comics")
        self._update_counts()
        self.scan_completed.emit(comics)

    def _on_scan_error(self, message, worker):
        if worker is self.worker:
            self.status_label.setText(message)

    def _on_enrich(self):
        from comicdesk.ui.api_key_prompt import ensure_api_key

        if not ensure_api_key(self, self.config, "Bulk metadata enrichment"):
            return
        answer = QMessageBox.question(self, "Confirm metadata update",
            f"Update and permanently save external metadata for all {len(self.comics)} comics?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.status_label.setText("Updating metadata for all comics…")
        self.enrich_btn.setEnabled(False)
        self.enrich_worker = EnrichWorker(
            self.comics,
            self.config.api_key,
            cache_enabled=self.config.cache_enabled,
            batch_update=True,
        )
        self.enrich_worker.finished.connect(self._on_enrich_complete)
        self.enrich_worker.error.connect(lambda msg: self.status_label.setText(f"Error: {msg}"))
        self.enrich_worker.progress.connect(
            lambda cur, total: self.status_label.setText(f"Enriching: {cur}/{total}"))
        self.enrich_worker.start()

    def _on_enrich_complete(self, comics: list[Comic], error_occurred: bool):
        enriched = sum(comic.has_cv_ids for comic in comics)
        self._set_comics(comics)
        self.set_reading_list(self.reading_list)
        self.enrich_btn.setEnabled(True)
        if not error_occurred:
            self.status_label.setText(f"Enriched {enriched}/{len(comics)} comics")
        self._update_counts()

    def _update_counts(self, *_args):
        selected = len(self.table.selectionModel().selectedRows())
        self.toolbar.set_counts(self.table.proxy_model.rowCount(), selected)
        self.add_selected_btn.setEnabled(selected > 0)
        self.clear_selection_btn.setEnabled(selected > 0)
        if selected:
            self.status_label.setText(f"{selected} comic(s) selected")
        self.comic_focused.emit(self._current_comic())

    def _emit_focus(self):
        self.comic_focused.emit(self._current_comic())

    def _set_comics(self, comics):
        """Replace model data while retaining identities still present."""
        self._selection.remember(self._selected_comics())
        self.comics = list(comics)
        self.model.set_comics(self.comics)
        self._restore_selection()
        self.comics_changed.emit(list(self.comics))

    def set_reading_list(self, reading_list):
        """Update the reading-list indicator for the current comic rows."""
        self.reading_list = reading_list
        self.model.set_reading_list(reading_list)

    update_reading_list = set_reading_list

    def _restore_selection(self):
        selection_model = self.table.selectionModel()
        selection_model.clearSelection()
        if not self._selection.paths:
            self._update_counts()
            return
        selection = QItemSelection()
        for row in range(self.table.proxy_model.rowCount()):
            index = self.table.proxy_model.index(row, 0)
            if self._selection.contains(self._comic_from_proxy(index)):
                selection.select(index, index)
        selection_model.select(selection, QItemSelectionModel.Select | QItemSelectionModel.Rows)
        self._update_counts()

    def _comic_from_proxy(self, index):
        if not index.isValid():
            return None
        source = self.table.proxy_model.mapToSource(index)
        if not source.isValid():
            return None
        return self.table.source_model.comic_at(source.row())

    def _selected_comics(self):
        return [comic for index in self.table.selectionModel().selectedRows()
                if (comic := self._comic_from_proxy(index)) is not None]

    def _show_context_menu(self, position):
        menu = QMenu(self)
        clicked_index = self.table.indexAt(position)
        selected = self._selected_comics()
        if selected:
            menu.addAction("➕ Add to Reading List", self._add_to_list)
            menu.addSeparator()
            menu.addAction("Edit metadata", self._request_edit)
        menu.addAction("🌐 Open CV URL", lambda: self._open_cv_url(clicked_index))
        menu.exec(self.table.viewport().mapToGlobal(position))

    def _current_comic(self):
        return self._comic_from_proxy(self.table.currentIndex())

    def _request_edit(self, *_args):
        comic = self._current_comic()
        if comic is not None:
            self.comic_edit_requested.emit(comic)

    def refresh_comic(self, comic):
        """Notify the table that an edited comic changed in place."""
        for row, current in enumerate(self.model.comics):
            if current is comic or current.path == comic.path:
                last_column = self.model.columnCount() - 1
                self.model.dataChanged.emit(
                    self.model.index(row, 0),
                    self.model.index(row, last_column),
                    [Qt.DisplayRole, Qt.EditRole, Qt.ToolTipRole],
                )
                self._update_counts()
                return

    def focus_comic(self, comic):
        """Focus a comic without destroying the user's multi-selection."""
        for row, current in enumerate(self.model.comics):
            if current is comic or current.path == comic.path:
                source = self.model.index(row, 0)
                proxy = self.table.proxy_model.mapFromSource(source)
                if proxy.isValid():
                    self.table.setCurrentIndex(proxy)
                    self.table.scrollTo(proxy)
                return

    def _add_to_list(self):
        selected = self._selected_comics()
        if selected:
            self.comics_selected.emit(selected)

    def _clear_selection(self):
        self.table.clearSelection()
        self._selection.clear()
        self._update_counts()
        self.status_label.setText("Selection cleared")

    def _open_cv_url(self, index=None):
        index = self.table.currentIndex() if index is None else index
        comic = self._comic_from_proxy(index) if index.isValid() else None
        if comic and comic.web_links:
            QDesktopServices.openUrl(comic.web_links[0])
