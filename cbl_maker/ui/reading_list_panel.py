import logging
from copy import copy, deepcopy
from pathlib import Path

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog, QHeaderView, QMessageBox, QPushButton, QSplitter,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from cbl_maker.config import Config
from cbl_maker.models import Comic, ReadingList
from cbl_maker.services.cbl_reader import CBLParseError, read_cbl, reconcile_cbl
from cbl_maker.services.cbl_writer import generate_cbl, save_cbl
from cbl_maker.services.wishlist import WishlistManager
from cbl_maker.ui.reading_list_header import ReadingListHeader
from cbl_maker.ui.reading_list_sort import ReadingListSort
from cbl_maker.ui.cbl_preview import CBLPreview
from cbl_maker.ui.reading_list_filename import safe_filename
from cbl_maker.ui.theme import colors_for, table_stylesheet

logger = logging.getLogger(__name__)
class ReadingListPanel(QWidget):
    """Panel for managing the reading list."""
    status_message = Signal(str)
    dirty_changed = Signal(bool)
    list_changed = Signal()
    wishlist_items_added = Signal(int)

    def __init__(self, config: Config | None = None):
        super().__init__()
        self.config = config or Config()
        self._theme = "dark"
        self._wishlist_manager: WishlistManager | None = None
        self.reading_list = ReadingList(name="New Reading List")
        self.available_comics = []
        self.is_dirty = False
        self._setup_ui()
        self._populate_table()
        self._update_preview()
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.header = ReadingListHeader(self.reading_list)
        self.name_label = self.header.name_edit
        self.count_label = self.header.count_label
        self.clear_btn = self.header.clear_btn
        self.export_btn = self.header.export_btn
        self.import_btn = self.header.import_btn
        self.export_btn.setObjectName("primaryExportButton")
        self.export_btn.setDefault(True)
        self.header.clear_requested.connect(self.clear_list)
        self.header.export_requested.connect(self.export_cbl)
        self.header.import_requested.connect(self.import_cbl)
        self.header.name_changed.connect(self._on_name_changed)
        layout.addWidget(self.header)

        self.controls = QWidget()
        controls_layout = QVBoxLayout(self.controls)
        controls_layout.setContentsMargins(12, 6, 12, 6)
        sort_row = ReadingListSort()
        sort_row.changed.connect(self._on_sort_changed)
        self.sort_controls = sort_row
        self.sort_combo = sort_row.criterion_combo
        self.direction_combo = sort_row.direction_combo
        self.sort_direction_combo = sort_row.direction_combo
        self.manual_check = sort_row.manual_check
        controls_layout.addWidget(sort_row)
        layout.addWidget(self.controls)

        self._setup_table()
        self.preview = CBLPreview()
        self.splitter = QSplitter(Qt.Vertical)
        self.splitter.addWidget(self.table)
        self.splitter.addWidget(self.preview)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 2)
        self.splitter.setSizes([420, 240])
        self.preview.maximize_requested.connect(self._maximize_preview)
        layout.addWidget(self.splitter, 1)
        self.apply_theme(self._theme)

    def apply_theme(self, theme: str) -> None:
        """Re-apply visual tokens for the active theme."""
        self._theme = theme
        c = colors_for(theme)
        self.controls.setStyleSheet(f"background-color: {c['canvas']};")
        self.table.setStyleSheet(table_stylesheet(theme))
        self.header.apply_theme(theme)
        self.sort_controls.apply_theme(theme)
        self.preview.apply_theme(theme)

    def _setup_table(self):
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["", "", "Comic", ""])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        for column in (0, 1, 3):
            header.setSectionResizeMode(column, QHeaderView.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
    def _button(self, text, slot):
        button = QPushButton(text)
        button.setFixedSize(26, 24)
        button.clicked.connect(slot)
        return button
    def _populate_table(self):
        self.table.setRowCount(len(self.reading_list.comics))
        last = len(self.reading_list.comics) - 1
        for row, comic in enumerate(self.reading_list.comics):
            up = self._button("▲", lambda _, r=row: self._move_up(r))
            down = self._button("▼", lambda _, r=row: self._move_down(r))
            can_move = self.reading_list.ordered_by == "manual"
            up.setEnabled(can_move and row > 0)
            down.setEnabled(can_move and row < last)
            self.table.setCellWidget(row, 0, up)
            self.table.setCellWidget(row, 1, down)
            self.table.setItem(row, 2, QTableWidgetItem(f"{comic.series_name} #{comic.issue_number}"))
            self.table.setCellWidget(row, 3, self._button("×", lambda _, r=row: self._remove_at(r)))
        self._update_count()
    def _update_count(self):
        self.header.set_count(len(self.reading_list.comics))

    def _on_sort_changed(self, index=None):
        previous = self._list_snapshot()
        if self.sort_controls.is_manual:
            self.reading_list.sort_by("manual")
        else:
            self.reading_list.sort_by(
                self.sort_combo.currentData(), self.direction_combo.currentData()
            )
        self._populate_table()
        self._update_preview()
        self._set_dirty(True)
        self._emit_list_changed_if_needed(previous)

    def _on_name_changed(self, _name):
        self._update_preview()
        self._set_dirty(True)
        self.list_changed.emit()
    def _set_dirty(self, dirty):
        """Track edits so the host window can expose unsaved changes."""
        dirty = bool(dirty)
        if self.is_dirty != dirty:
            self.is_dirty = dirty
            self.dirty_changed.emit(dirty)
    def _list_snapshot(self): return deepcopy(self.reading_list)
    def _emit_list_changed_if_needed(self, previous):
        self.list_changed.emit() if self.reading_list != previous else None
    def add_comic(self, comic: Comic):
        if self.reading_list.add_comic(comic):
            self._apply_current_order()
            self._populate_table()
            self._update_preview()
            self._set_dirty(True)
            self.list_changed.emit()
        else:
            QMessageBox.information(self, "Duplicate", "This comic is already in the list")
    def set_available_comics(self, comics):
        self.available_comics = list(comics or [])

    def set_wishlist_manager(self, manager: WishlistManager | None) -> None:
        self._wishlist_manager = manager

    def shutdown_workers(self):
        """Stop work owned by this panel before the window closes."""
        return None
    def _loaded_comics(self):
        if self.available_comics:
            return self.available_comics
        window = self.window()
        comic_list = getattr(window, "comic_list", None)
        return list(getattr(comic_list, "comics", []) or [])

    def _cbl_start_directory(self) -> str:
        """Return the best starting directory for CBL file dialogs."""
        if self.config.last_cbl_directory:
            return self.config.last_cbl_directory
        if self.config.default_folder:
            return self.config.default_folder
        return ""

    def _persist_cbl_directory(self, file_path: str) -> None:
        """Save the parent directory of *file_path* as the last CBL directory."""
        directory = str(Path(file_path).parent)
        if directory != self.config.last_cbl_directory:
            self.config.last_cbl_directory = directory
            try:
                self.config.save()
            except OSError:
                logger.debug("Could not persist last CBL directory", exc_info=True)

    def import_cbl(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open CBL File", self._cbl_start_directory(),
            "CBL Files (*.cbl);;All Files (*)"
        )
        if not path:
            return
        self._persist_cbl_directory(path)
        previous = self._list_snapshot()
        try:
            document = read_cbl(Path(path))
            scanned = self._loaded_comics()
            staged = [copy(comic) for comic in scanned]
            staged_to_original = {
                id(staged_comic): comic
                for staged_comic, comic in zip(staged, scanned)
            }
            result = reconcile_cbl(document, staged)
        except (CBLParseError, OSError, ValueError) as error:
            logger.exception("Unable to import CBL from %s", path)
            self.status_message.emit(f"Import failed: {error}")
            return

        wishlist_summary = ""
        if document.books and not result.missing_files:
            QMessageBox.information(
                self,
                "Import CBL",
                "All issues in this reading list are already available in your local library.",
            )
        elif result.missing_files and self._wishlist_manager is not None:
            add_result = self._wishlist_manager.add_books(result.missing_files)
            if add_result.added:
                self.wishlist_items_added.emit(add_result.added)
            wishlist_summary = (
                f"Wishlist: {add_result.added} added"
                f"{f', {add_result.skipped_duplicates} duplicate(s) skipped' if add_result.skipped_duplicates else ''}"
                f" (see GetComics tab).\n"
            )

        summary = (
            f"Matches: {len(result.matches)}\n"
            f"New: {len(result.new_issues)}\n"
            f"Not located: {len(result.missing_files)}\n"
        )
        if wishlist_summary:
            summary += f"\n{wishlist_summary}"
        summary += f"\nUpdate the reading list with {len(result.matches)} located comics?"
        title = "Update Reading List"
        if self.is_dirty:
            summary = "The current reading list has unsaved changes.\n\n" + summary
        answer = QMessageBox.question(
            self, title, summary,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        matches = []
        for matched in result.matches:
            comic = staged_to_original.get(id(matched), matched)
            if comic is not matched:
                if not comic.cv_series_id and matched.cv_series_id:
                    comic.cv_series_id = matched.cv_series_id
                if not comic.cv_issue_id and matched.cv_issue_id:
                    comic.cv_issue_id = matched.cv_issue_id
                if comic.cv_metadata is None and matched.cv_metadata is not None:
                    comic.cv_metadata = matched.cv_metadata
            matches.append(comic)
        self.reading_list = ReadingList(
            name=document.name,
            comics=matches,
            ordered_by=document.ordered_by,
            order_direction=document.order_direction,
        )
        self.header.set_reading_list(self.reading_list)
        self._sync_sort_controls()
        self._populate_table()
        self._update_preview()
        self._set_dirty(True)
        self._emit_list_changed_if_needed(previous)
        status = f"Imported {len(result.matches)} comics; {len(result.missing_files)} not located"
        if wishlist_summary:
            status += f"; wishlist updated"
        self.status_message.emit(status)
    def _sync_sort_controls(self):
        criterion = self.reading_list.ordered_by
        blockers = (QSignalBlocker(self.manual_check), QSignalBlocker(self.sort_combo),
                    QSignalBlocker(self.direction_combo))
        try:
            self.manual_check.setChecked(criterion == "manual")
            if criterion == "manual":
                return
            for combo, data in ((self.sort_combo, criterion),
                                (self.direction_combo, self.reading_list.order_direction)):
                index = combo.findData(data)
                if index >= 0:
                    combo.setCurrentIndex(index)
        finally:
            del blockers
    def _move_up(self, row):
        if self.reading_list.ordered_by == "manual" and row > 0:
            previous = self._list_snapshot()
            self.reading_list.move_comic(self.reading_list.comics[row], -1)
            self._populate_table(); self._update_preview(); self._set_dirty(True)
            self._emit_list_changed_if_needed(previous)
    def _move_down(self, row):
        if self.reading_list.ordered_by == "manual" and row < len(self.reading_list.comics) - 1:
            previous = self._list_snapshot()
            self.reading_list.move_comic(self.reading_list.comics[row], 1)
            self._populate_table(); self._update_preview(); self._set_dirty(True)
            self._emit_list_changed_if_needed(previous)
    def _remove_at(self, row):
        if 0 <= row < len(self.reading_list.comics):
            previous = self._list_snapshot()
            self.reading_list.comics.pop(row)
            self._populate_table(); self._update_preview(); self._set_dirty(True)
            self._emit_list_changed_if_needed(previous)
    def clear_list(self):
        if not self.reading_list.comics:
            return
        previous = self._list_snapshot()
        self.reading_list.comics.clear()
        self._populate_table()
        self._update_preview()
        self._set_dirty(True)
        self._emit_list_changed_if_needed(previous)
    def _apply_current_order(self):
        if self.sort_controls.is_manual:
            self.reading_list.sort_by("manual")
        else:
            self.reading_list.sort_by(
                self.sort_combo.currentData(), self.direction_combo.currentData()
            )
    def _update_preview(self):
        content = generate_cbl(self.reading_list) if self.reading_list.comics else ""
        self.preview.set_content(content)
    def _maximize_preview(self):
        self.splitter.setSizes([max(1, self.table.minimumHeight()), max(180, self.height())])

    def export_cbl(self):
        """Export the current list, reporting outcomes without modal success UI."""
        if not self.reading_list.comics:
            self.status_message.emit("Nothing to export: the reading list is empty")
            return

        default_name = self._safe_filename(self.reading_list.name)
        start = str(Path(self._cbl_start_directory()) / f"{default_name}.cbl") \
            if self._cbl_start_directory() else f"{default_name}.cbl"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save CBL File", start,
            "CBL Files (*.cbl);;All Files (*)",
        )
        if path:
            self._persist_cbl_directory(path)
            try:
                save_cbl(generate_cbl(self.reading_list), Path(path))
            except OSError as error:
                logger.exception("Unable to export CBL to %s", path)
                self.status_message.emit(f"Export failed: {error}")
                return
            self._set_dirty(False)
            self.status_message.emit(f"Exported reading list to {path}")

    @staticmethod
    def _safe_filename(name):
        return safe_filename(name)
