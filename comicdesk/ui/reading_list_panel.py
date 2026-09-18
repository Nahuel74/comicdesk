import logging
from copy import copy, deepcopy
from pathlib import Path

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFileDialog,
    QHeaderView,
    QMessageBox,
    QSizePolicy,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from comicdesk.config import Config
from comicdesk.models import Comic, ReadingList
from comicdesk.services.cbl_reader import (
    CBLParseError,
    ordered_comics_for_import,
    read_cbl,
    reconcile_cbl,
)
from comicdesk.services.cbl_writer import generate_cbl, save_cbl
from comicdesk.services.wishlist import WishlistManager
from comicdesk.ui.add_reading_list_issue_dialog import AddReadingListIssueDialog
from comicdesk.ui.reading_list_header import ReadingListHeader
from comicdesk.ui.reading_list_sort import ReadingListSort
from comicdesk.ui.cbl_preview import CBLPreview
from comicdesk.ui.reading_list_filename import safe_filename
from comicdesk.ui.reading_list_table_model import ReadingListTableModel
from comicdesk.ui.theme import button_stylesheet, colors_for, table_stylesheet

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
        self._source_cbl_path: Path | None = None
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
        self.save_btn = self.header.save_btn
        self.export_btn = self.header.export_btn
        self.import_btn = self.header.import_btn
        self.add_issue_btn = self.header.add_issue_btn
        self.save_btn.setObjectName("primarySaveButton")
        self.save_btn.setDefault(True)
        self.header.clear_requested.connect(self.clear_list)
        self.header.save_requested.connect(self.save_list)
        self.header.export_requested.connect(self.export_cbl)
        self.header.import_requested.connect(self.import_cbl)
        self.header.add_issue_requested.connect(self._add_issue_dialog)
        self.header.name_changed.connect(self._on_name_changed)
        layout.addWidget(self.header)

        self.controls = QWidget()
        controls_layout = QVBoxLayout(self.controls)
        controls_layout.setContentsMargins(12, 6, 12, 6)
        sort_row = ReadingListSort()
        sort_row.apply_requested.connect(self._apply_sort)
        sort_row.remove_requested.connect(self._remove_selected)
        self.sort_controls = sort_row
        self.sort_combo = sort_row.criterion_combo
        self.direction_combo = sort_row.direction_combo
        self.sort_direction_combo = sort_row.direction_combo
        self.apply_sort_btn = sort_row.apply_button
        controls_layout.addWidget(sort_row)
        layout.addWidget(self.controls)

        self._setup_table()
        self.preview = CBLPreview()
        self._table_pane = QWidget()
        table_pane_layout = QVBoxLayout(self._table_pane)
        table_pane_layout.setContentsMargins(12, 0, 12, 12)
        table_pane_layout.setSpacing(0)
        table_pane_layout.addWidget(self.table)

        self.preview.setMinimumWidth(self._PREVIEW_PANE_MIN_WIDTH)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.addWidget(self._table_pane)
        self.splitter.addWidget(self.preview)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setStretchFactor(0, 2)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([720, self._PREVIEW_PANE_DEFAULT_WIDTH])
        layout.addWidget(self.splitter, 1)
        self.apply_theme(self._theme)

    def apply_theme(self, theme: str) -> None:
        """Re-apply visual tokens for the active theme."""
        self._theme = theme
        c = colors_for(theme)
        self.controls.setStyleSheet(f"background-color: {c['canvas']};")
        self.table.setStyleSheet(table_stylesheet(theme))
        self._table_model.set_muted_color(QColor(c["muted"]))
        if self._table_model.rowCount() > 0:
            self._table_model.refresh()
        self.header.apply_theme(theme)
        self.sort_controls.apply_theme(theme)
        self.preview.apply_theme(theme)
        self.save_btn.setStyleSheet(button_stylesheet(theme, "primary"))

    _ROW_HEIGHT = 36
    _PREVIEW_PANE_MIN_WIDTH = 260
    _PREVIEW_PANE_DEFAULT_WIDTH = 350

    _COL_NUM = ReadingListTableModel.COL_NUM
    _COL_SERIES = ReadingListTableModel.COL_SERIES
    _COL_VOLUME = ReadingListTableModel.COL_VOLUME
    _COL_ISSUE = ReadingListTableModel.COL_ISSUE
    _COL_TITLE = ReadingListTableModel.COL_TITLE
    _COL_RELEASE = ReadingListTableModel.COL_RELEASE
    _COL_FILE = ReadingListTableModel.COL_FILE

    def _setup_table(self):
        self._table_model = ReadingListTableModel(self)
        self._table_model.manual_order_changed.connect(self._on_manual_drag_reorder)
        self.table = QTableView()
        self.table.setModel(self._table_model)
        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setMinimumSectionSize(36)
        for column in (self._COL_SERIES, self._COL_FILE):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Stretch)
        for column in (
            self._COL_NUM,
            self._COL_VOLUME,
            self._COL_ISSUE,
            self._COL_TITLE,
            self._COL_RELEASE,
        ):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setViewportMargins(0, 0, 2, 0)
        self.table.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        vheader = self.table.verticalHeader()
        vheader.setVisible(False)
        vheader.setDefaultSectionSize(self._ROW_HEIGHT)
        vheader.setMinimumSectionSize(self._ROW_HEIGHT)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.table.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.table.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.table.setDragDropOverwriteMode(False)
        self.table.setDropIndicatorShown(True)
        self.table.selectionModel().selectionChanged.connect(self._update_reorder_controls)

    def _selected_row(self) -> int:
        index = self.table.currentIndex()
        return index.row() if index.isValid() else -1

    def _cell_text(self, row: int, column: int) -> str:
        index = self._table_model.index(row, column)
        value = self._table_model.data(index, Qt.ItemDataRole.DisplayRole)
        return value if value is not None else ""

    def _populate_table(self):
        selected = self._selected_row()
        self._table_model.set_reading_list(self.reading_list)
        if 0 <= selected < len(self.reading_list.comics):
            self.table.selectRow(selected)
        self.sort_controls.set_order_state(self.reading_list.ordered_by == "manual")
        self._update_count()
        self._update_reorder_controls()

    def _on_manual_drag_reorder(self) -> None:
        previous = self._list_snapshot()
        self._update_preview()
        self._set_dirty(True)
        self.sort_controls.set_order_state(True)
        self._emit_list_changed_if_needed(previous)

    def _apply_sort(self):
        previous = self._list_snapshot()
        self.reading_list.sort_by(self.sort_combo.currentData(), self.direction_combo.currentData())
        self._populate_table()
        self._update_preview()
        self._set_dirty(True)
        self._emit_list_changed_if_needed(previous)
    def _update_count(self):
        self.header.set_count(len(self.reading_list.comics))

    def _on_name_changed(self, _name):
        self._update_preview()
        self._set_dirty(True)
        self.list_changed.emit()
    def _set_dirty(self, dirty):
        """Track edits so the host window can expose unsaved changes."""
        dirty = bool(dirty)
        if self.is_dirty != dirty:
            self.is_dirty = dirty
            self.header.set_dirty(dirty)
            self.dirty_changed.emit(dirty)
    def _list_snapshot(self): return deepcopy(self.reading_list)
    def _emit_list_changed_if_needed(self, previous):
        self.list_changed.emit() if self.reading_list != previous else None
    def add_comic(self, comic: Comic) -> bool:
        if self.reading_list.add_comic(comic):
            self._apply_current_order()
            self._populate_table()
            self._update_preview()
            self._set_dirty(True)
            self.list_changed.emit()
            return True
        QMessageBox.information(self, "Duplicate", "This comic is already in the list")
        return False
    def set_available_comics(self, comics):
        self.available_comics = list(comics or [])

    def set_wishlist_manager(self, manager: WishlistManager | None) -> None:
        self._wishlist_manager = manager

    def _add_issue_dialog(self) -> None:
        dialog = AddReadingListIssueDialog(self.config, self)
        dialog.apply_theme(self._theme)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        comic = dialog.built_comic()
        if comic is not None:
            self.add_comic(comic)

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

        linked = len(result.matches)
        missing = len(result.missing_files)
        total = linked + missing

        summary = (
            f"This reading list has {total} issue"
            f"{'' if total == 1 else 's'}: {linked} linked to files in your library, "
            f"{missing} not found on disk.\n\n"
            "Replace the current reading list with this import?"
        )
        title = "Import Reading List"
        if self.is_dirty:
            summary = "The current reading list has unsaved changes.\n\n" + summary
        answer = QMessageBox.question(
            self, title, summary,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        wishlist_repaired = 0
        if self._wishlist_manager is not None:
            wishlist_repaired = self._wishlist_manager.repair_from_books(document.books)

        wishlist_added = 0
        if missing > 0 and self._wishlist_manager is not None:
            wishlist_answer = QMessageBox.question(
                self,
                "Add to Wishlist",
                f"Add the {missing} missing issue"
                f"{'' if missing == 1 else 's'} to your Wishlist?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if wishlist_answer == QMessageBox.StandardButton.Yes:
                add_result = self._wishlist_manager.add_books(result.missing_files)
                wishlist_added = add_result.added
                if add_result.added:
                    self.wishlist_items_added.emit(add_result.added)

        ordered = ordered_comics_for_import(document, staged)
        comics = []
        for entry in ordered:
            if entry.has_local_file:
                comic = staged_to_original.get(id(entry), entry)
                if comic is not entry:
                    if not comic.cv_series_id and entry.cv_series_id:
                        comic.cv_series_id = entry.cv_series_id
                    if not comic.cv_issue_id and entry.cv_issue_id:
                        comic.cv_issue_id = entry.cv_issue_id
                    if comic.cv_metadata is None and entry.cv_metadata is not None:
                        comic.cv_metadata = entry.cv_metadata
                comics.append(comic)
            else:
                comics.append(entry)
        self.reading_list = ReadingList(
            name=document.name,
            comics=comics,
            ordered_by=document.ordered_by,
            order_direction=document.order_direction,
        )
        self.header.set_reading_list(self.reading_list)
        self._source_cbl_path = Path(path)
        self._sync_sort_controls()
        self._populate_table()
        self._update_preview()
        self._set_dirty(True)
        self._emit_list_changed_if_needed(previous)
        status = (
            f"Imported reading list: {linked} linked, {missing} not in library"
        )
        if wishlist_repaired:
            status += f"; {wishlist_repaired} wishlist item(s) updated"
        if wishlist_added:
            status += f"; {wishlist_added} added to wishlist"
        self.status_message.emit(status)
    def _sync_sort_controls(self):
        criterion = self.reading_list.ordered_by
        blockers = (
            QSignalBlocker(self.sort_combo),
            QSignalBlocker(self.direction_combo),
        )
        try:
            self.sort_controls.set_order_state(criterion == "manual")
            if criterion == "manual":
                return
            for combo, data in (
                (self.sort_combo, criterion),
                (self.direction_combo, self.reading_list.order_direction),
            ):
                index = combo.findData(data)
                if index >= 0:
                    combo.setCurrentIndex(index)
        finally:
            del blockers

    def _update_reorder_controls(self) -> None:
        row = self._selected_row()
        enabled = row >= 0 and bool(self.reading_list.comics)
        self.sort_controls.set_reorder_enabled(enabled)

    def _remove_selected(self) -> None:
        row = self._selected_row()
        if row >= 0:
            self._remove_at(row)
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
        if self.reading_list.ordered_by != "manual":
            self.reading_list.sort_by(
                self.sort_combo.currentData(), self.direction_combo.currentData()
            )
    def _update_preview(self):
        content = generate_cbl(self.reading_list) if self.reading_list.comics else ""
        self.preview.set_content(content)
    def save_list(self) -> None:
        """Save to the imported CBL path, or prompt for a path like export."""
        if not self.reading_list.comics:
            self.status_message.emit("Nothing to save: the reading list is empty")
            return
        if self._source_cbl_path is not None:
            if self._write_cbl(self._source_cbl_path):
                self.status_message.emit(f"Saved reading list to {self._source_cbl_path}")
            return
        self.export_cbl()

    def _write_cbl(self, path: Path, action: str = "Save") -> bool:
        try:
            save_cbl(generate_cbl(self.reading_list), path)
        except OSError as error:
            logger.exception("Unable to write CBL to %s", path)
            self.status_message.emit(f"{action} failed: {error}")
            return False
        self._persist_cbl_directory(str(path))
        self._set_dirty(False)
        return True

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
            target = Path(path)
            if self._write_cbl(target, action="Export"):
                self.status_message.emit(f"Exported reading list to {path}")

    @staticmethod
    def _safe_filename(name):
        return safe_filename(name)
