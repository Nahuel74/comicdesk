"""Comic list panel with search, filtering, and library actions."""

import os
from pathlib import Path

from PySide6.QtCore import QItemSelection, QItemSelectionModel, Signal, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QHeaderView, QLabel, QMenu, QProgressBar, QPushButton,
    QTableView, QHBoxLayout, QMessageBox, QVBoxLayout, QWidget,
)

from comicdesk.models import Comic
from comicdesk.ui.comic_list_toolbar import ComicListToolbar
from comicdesk.ui.comic_list_workers import FolderRenameWorker, RenameWorker, ScanWorker
from comicdesk.ui.rename_files_dialog import RenameFilesDialog
from comicdesk.ui.comic_table_model import ComicFilterProxyModel, ComicTableModel
from comicdesk.ui.comic_selection import ComicSelection
from comicdesk.ui.theme import button_stylesheet, muted_label_stylesheet, table_stylesheet
from comicdesk.ui.widgets.responsive_action_bar import ResponsiveActionBar


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
    files_renamed = Signal(list)
    library_root_renamed = Signal(object, object)

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
        self.add_selected_btn = QPushButton("Add to list")
        self.add_selected_btn.setToolTip("Add the selected comics to the reading list")
        self.add_selected_btn.setEnabled(False)
        self.add_selected_btn.clicked.connect(self._add_to_list)
        self.clear_selection_btn = QPushButton("Clear selection")
        self.clear_selection_btn.setToolTip("Clear the current comic selection")
        self.clear_selection_btn.setEnabled(False)
        self.clear_selection_btn.clicked.connect(self._clear_selection)
        self.rename_btn = QPushButton("Rename files…")
        self.rename_btn.setToolTip(
            "Rename selected comic files using a metadata template (or all comics if none selected)"
        )
        self.rename_btn.setEnabled(False)
        self.rename_btn.clicked.connect(self._on_rename_files)
        self.rename_folders_btn = QPushButton("Rename folders…")
        self.rename_folders_btn.setToolTip(
            "Rename series folders using a metadata template (or all comics if none selected)"
        )
        self.rename_folders_btn.setEnabled(False)
        self.rename_folders_btn.clicked.connect(self._on_rename_folders)
        self.action_bar.add_action(self.rename_btn, "Rename files")
        self.action_bar.add_action(self.rename_folders_btn, "Rename folders")
        self.action_bar.add_action(self.add_selected_btn, "Add to reading list")
        self.action_bar.add_action(self.clear_selection_btn, "Clear selection")
        actions_layout.addWidget(self.action_bar, 1)
        layout.addWidget(actions_row)
        layout.addWidget(self.toolbar)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        layout.addWidget(self.table)
        self.scan_progress = QProgressBar()
        self.scan_progress.setFixedHeight(8)
        self.scan_progress.setTextVisible(False)
        self.scan_progress.hide()
        layout.addWidget(self.scan_progress)
        self.status_label = QLabel("No comics loaded")
        layout.addWidget(self.status_label)
        self.apply_theme(self._theme)

    def apply_theme(self, theme: str) -> None:
        """Re-apply visual tokens for the active theme."""
        self._theme = theme
        self.rename_btn.setStyleSheet(button_stylesheet(theme, "default"))
        self.rename_folders_btn.setStyleSheet(button_stylesheet(theme, "default"))
        self.table.setStyleSheet(table_stylesheet(theme))
        self.status_label.setStyleSheet(
            muted_label_stylesheet(theme) + " padding: 8px 12px;"
        )
        self.toolbar.apply_theme(theme)
        self.action_bar.apply_theme(theme)

    def load_folder(self, path: Path):
        self.current_folder = path
        self._stop_scan_worker()
        self._set_scan_busy(True)
        self.status_label.setText("Loading library…")
        self.worker = ScanWorker(path)
        worker = self.worker
        self._scan_finished_handler = lambda comics: self._on_scan_complete(comics, worker)
        self._scan_progress_handler = (
            lambda current, total, name: self._on_scan_progress(current, total, name, worker)
        )
        worker.finished.connect(self._scan_finished_handler)
        worker.progress.connect(self._scan_progress_handler)
        worker.error.connect(lambda message, w=worker: self._on_scan_error(message, w))
        worker.start()

    def _stop_scan_worker(self):
        """Cancel and reap a previous scan before starting another one."""
        was_busy = getattr(self, "worker", None) is not None
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
        if was_busy:
            self._set_scan_busy(False)

    def _stop_rename_worker(self):
        worker = getattr(self, "rename_worker", None)
        if worker is None:
            return
        worker.cancel()
        if worker.isRunning():
            worker.wait()
        worker.deleteLater()
        self.rename_worker = None

    def _stop_folder_rename_worker(self):
        worker = getattr(self, "folder_rename_worker", None)
        if worker is None:
            return
        worker.cancel()
        if worker.isRunning():
            worker.wait()
        worker.deleteLater()
        self.folder_rename_worker = None

    def shutdown_workers(self):
        """Synchronously stop every worker owned by this panel."""
        self._stop_scan_worker()
        self._stop_rename_worker()
        self._stop_folder_rename_worker()

    def _set_scan_busy(self, busy: bool) -> None:
        self.scan_progress.setVisible(busy)
        if busy:
            self.scan_progress.setRange(0, 0)
            self.scan_progress.setValue(0)
        else:
            self.scan_progress.setRange(0, 100)
            self.scan_progress.setValue(0)
        self.table.setEnabled(not busy)
        self.rename_btn.setEnabled(not busy and bool(self.comics))
        self.rename_folders_btn.setEnabled(
            not busy and bool(self.comics) and self.current_folder is not None
        )
        self.toolbar.setEnabled(not busy)

    def _on_scan_progress(self, current, total, name, worker):
        if worker is not self.worker:
            return
        if total > 0:
            self.scan_progress.setRange(0, total)
            self.scan_progress.setValue(current)
        if current <= 0:
            self.status_label.setText("Loading library…")
        elif name:
            self.status_label.setText(f"Loading library… ({current}/{total}) — {name}")
        else:
            self.status_label.setText(f"Loading library… ({current}/{total})")

    def _on_scan_complete(self, comics: list[Comic], worker=None):
        if worker is not None and worker is not self.worker:
            return
        self._set_scan_busy(False)
        self.comics = comics
        self._set_comics(comics)
        self.set_reading_list(self.reading_list)
        self.status_label.setText(f"Found {len(comics)} comics")
        self._update_counts()
        self._update_rename_enabled()
        self.scan_completed.emit(comics)

    def _on_scan_error(self, message, worker):
        if worker is self.worker:
            self.status_label.setText(message)

    def _update_counts(self, *_args):
        selected = len(self.table.selectionModel().selectedRows())
        self.toolbar.set_counts(self.table.proxy_model.rowCount(), selected)
        self.add_selected_btn.setEnabled(selected > 0)
        self.clear_selection_btn.setEnabled(selected > 0)
        self._update_rename_enabled()
        if selected:
            self.status_label.setText(f"{selected} comic(s) selected")
        self.comic_focused.emit(self._current_comic())

    def _update_rename_enabled(self):
        has_local = any(comic.has_local_file for comic in self.comics)
        self.rename_btn.setEnabled(has_local)
        self.rename_folders_btn.setEnabled(
            has_local and self.current_folder is not None
        )

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
            menu.addAction("Rename files…", self._on_rename_files)
            menu.addAction("Rename folders…", self._on_rename_folders)
            menu.addAction("Edit metadata", self._request_edit)
        menu.addAction("🌐 Open CV URL", lambda: self._open_cv_url(clicked_index))
        menu.exec(self.table.viewport().mapToGlobal(position))

    def _current_comic(self):
        return self._comic_from_proxy(self.table.currentIndex())

    def _request_edit(self, *_args):
        comic = self._current_comic()
        if comic is not None:
            self.comic_edit_requested.emit(comic)

    def refresh_comic(self, comic, previous_path: str = ""):
        """Notify the table that an edited comic changed in place."""
        if previous_path and str(comic.path) != previous_path:
            self._selection.remap_paths({previous_path: str(comic.path)})
        for row, current in enumerate(self.model.comics):
            if current is comic or current.path == comic.path or (
                previous_path and str(current.path) == previous_path
            ):
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

    def _rename_targets(self) -> list[Comic]:
        selected = self._selected_comics()
        pool = selected if selected else list(self.comics)
        return [comic for comic in pool if comic.has_local_file]

    def _on_rename_files(self):
        targets = self._rename_targets()
        if not targets:
            QMessageBox.information(
                self,
                "Rename files",
                "No local comic files to rename in the current selection or folder.",
            )
            return
        dialog = RenameFilesDialog(
            targets,
            config=self.config,
            target_count=len(targets),
            theme=self._theme,
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        if self.config is not None:
            self.config.last_rename_template = dialog.template_text()
            self.config.rename_issue_pad_width = dialog.issue_pad_width()
            self.config.save()
        rows = dialog.plan_rows()
        self.status_label.setText("Renaming files…")
        self.rename_btn.setEnabled(False)
        self.rename_worker = RenameWorker(rows)
        self.rename_worker.progress.connect(
            lambda current, total, name: self.status_label.setText(
                f"Renaming: {current}/{total} — {name}"
            )
        )
        self.rename_worker.finished.connect(self._on_rename_complete)
        self.rename_worker.start()

    def _remap_comic_paths_under_folder(
        self, old_folder: Path, new_folder: Path
    ) -> dict[str, str]:
        prefix_old = str(old_folder.resolve())
        prefix_new = str(new_folder.resolve())
        mapping: dict[str, str] = {}
        for comic in self.comics:
            path_str = str(comic.path.resolve())
            if path_str == prefix_old or path_str.startswith(prefix_old + os.sep):
                suffix = path_str[len(prefix_old) :]
                new_path = Path(prefix_new + suffix)
                mapping[str(comic.path)] = str(new_path)
                comic.path = new_path
        return mapping

    def _on_rename_folders(self):
        if self.current_folder is None:
            QMessageBox.information(
                self,
                "Rename folders",
                "Open a library folder before renaming series folders.",
            )
            return
        targets = self._rename_targets()
        if not targets:
            QMessageBox.information(
                self,
                "Rename folders",
                "No local comic files to rename in the current selection or folder.",
            )
            return
        dialog = RenameFilesDialog(
            targets,
            config=self.config,
            target_count=len(targets),
            theme=self._theme,
            mode="folders",
            library_root=self.current_folder,
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        if self.config is not None:
            self.config.last_rename_folder_template = dialog.template_text()
            self.config.rename_issue_pad_width = dialog.issue_pad_width()
            self.config.save()
        rows = dialog.folder_plan_rows()
        self.status_label.setText("Renaming folders…")
        self.rename_folders_btn.setEnabled(False)
        self.rename_btn.setEnabled(False)
        self.folder_rename_worker = FolderRenameWorker(rows, self.current_folder)
        self.folder_rename_worker.progress.connect(
            lambda current, total, name: self.status_label.setText(
                f"Renaming folders: {current}/{total} — {name}"
            )
        )
        self.folder_rename_worker.finished.connect(self._on_folder_rename_complete)
        self.folder_rename_worker.start()

    def _on_folder_rename_complete(self, results):
        mapping: dict[str, str] = {}
        failures = 0
        renamed_comics: list[Comic] = []
        root_old: Path | None = None
        root_new: Path | None = None
        for result in results:
            if result.error or result.folder_new is None:
                failures += 1
                continue
            row = result.row
            folder_mapping = self._remap_comic_paths_under_folder(
                row.folder_old, result.folder_new
            )
            mapping.update(folder_mapping)
            for comic in row.comics:
                if comic not in renamed_comics:
                    renamed_comics.append(comic)
            if result.library_root_new is not None:
                root_old = result.library_root_old
                root_new = result.library_root_new
        for comic in self.comics:
            if str(comic.path) in mapping.values():
                self.refresh_comic(comic)
        if mapping:
            self._selection.remap_paths(mapping)
            self._restore_selection()
        if root_new is not None and root_old is not None:
            self.current_folder = root_new
            self.library_root_renamed.emit(root_old, root_new)
        self.folder_rename_worker = None
        self._update_rename_enabled()
        success = len([r for r in results if r.folder_new and not r.error])
        if failures:
            self.status_label.setText(
                f"Renamed {success} folder(s); {failures} failed"
            )
        else:
            self.status_label.setText(f"Renamed {success} folder(s)")
        if renamed_comics:
            self.files_renamed.emit(renamed_comics)
            self.comics_changed.emit(list(self.comics))
        self._update_counts()

    def _on_rename_complete(self, results):
        mapping: dict[str, str] = {}
        renamed_comics: list[Comic] = []
        failures = 0
        for result in results:
            if result.new_path is not None:
                mapping[str(result.old_path)] = str(result.new_path)
                result.comic.path = result.new_path
                renamed_comics.append(result.comic)
                self.refresh_comic(result.comic)
            else:
                failures += 1
        if mapping:
            self._selection.remap_paths(mapping)
            self._restore_selection()
        self.rename_worker = None
        self._update_rename_enabled()
        success = len(renamed_comics)
        if failures:
            self.status_label.setText(
                f"Renamed {success} file(s); {failures} failed"
            )
        else:
            self.status_label.setText(f"Renamed {success} file(s)")
        if renamed_comics:
            self.files_renamed.emit(renamed_comics)
            self.comics_changed.emit(list(self.comics))
        self._update_counts()

    def _open_cv_url(self, index=None):
        index = self.table.currentIndex() if index is None else index
        comic = self._comic_from_proxy(index) if index.isValid() else None
        if comic and comic.web_links:
            QDesktopServices.openUrl(comic.web_links[0])
