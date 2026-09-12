import logging
from copy import copy, deepcopy
from pathlib import Path

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from comicdesk.config import Config
from comicdesk.models import Comic, ReadingList
from comicdesk.services.cbl_reader import CBLParseError, read_cbl, reconcile_cbl
from comicdesk.services.cbl_writer import generate_cbl, save_cbl
from comicdesk.services.wishlist import WishlistManager
from comicdesk.ui.reading_list_header import ReadingListHeader
from comicdesk.ui.reading_list_sort import ReadingListSort
from comicdesk.ui.cbl_preview import CBLPreview
from comicdesk.ui.reading_list_filename import safe_filename
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
        self.save_btn.setObjectName("primarySaveButton")
        self.save_btn.setDefault(True)
        self.header.clear_requested.connect(self.clear_list)
        self.header.save_requested.connect(self.save_list)
        self.header.export_requested.connect(self.export_cbl)
        self.header.import_requested.connect(self.import_cbl)
        self.header.name_changed.connect(self._on_name_changed)
        layout.addWidget(self.header)

        self.controls = QWidget()
        controls_layout = QVBoxLayout(self.controls)
        controls_layout.setContentsMargins(12, 6, 12, 6)
        sort_row = ReadingListSort()
        sort_row.apply_requested.connect(self._apply_sort)
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
        self.splitter.setSizes([650, self._PREVIEW_PANE_DEFAULT_WIDTH])
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
        self.save_btn.setStyleSheet(button_stylesheet(theme, "primary"))

    _COL_UP = 0
    _COL_DOWN = 1
    _COL_NUM = 2
    _COL_SERIES = 3
    _COL_VOLUME = 4
    _COL_ISSUE = 5
    _COL_TITLE = 6
    _COL_RELEASE = 7
    _COL_FILE = 8
    _COL_REMOVE = 9
    _ACTION_COL_WIDTH = 36
    _DOWN_COL_WIDTH = 40
    _REMOVE_COL_WIDTH = 46
    _REMOVE_CELL_RIGHT_PAD = 8
    _ROW_HEIGHT = 36
    _ACTION_BUTTON_SIZE = 24
    _PREVIEW_PANE_MIN_WIDTH = 260
    _PREVIEW_PANE_DEFAULT_WIDTH = 350

    def _setup_table(self):
        self.table = QTableWidget(0, 10)
        self.table.setHorizontalHeaderLabels([
            "", "", "#", "Series", "Volume", "Issue", "Title", "Release Date", "File", "",
        ])
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
        header.setSectionResizeMode(self._COL_UP, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(self._COL_UP, self._ACTION_COL_WIDTH)
        header.setSectionResizeMode(self._COL_DOWN, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(self._COL_DOWN, self._DOWN_COL_WIDTH)
        header.setSectionResizeMode(self._COL_REMOVE, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(self._COL_REMOVE, self._REMOVE_COL_WIDTH)
        self.table.setViewportMargins(0, 0, 2, 0)
        self.table.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        vheader = self.table.verticalHeader()
        vheader.setVisible(False)
        vheader.setDefaultSectionSize(self._ROW_HEIGHT)
        vheader.setMinimumSectionSize(self._ROW_HEIGHT)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setHorizontalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)

    def _row_icon_button(self, icon: QStyle.StandardPixmap, tooltip: str, slot) -> QPushButton:
        button = QPushButton()
        button.setIcon(self.style().standardIcon(icon))
        button.setFixedSize(self._ACTION_BUTTON_SIZE, self._ACTION_BUTTON_SIZE)
        button.setToolTip(tooltip)
        button.setStyleSheet(button_stylesheet(self._theme, "compact"))
        button.clicked.connect(slot)
        return button

    def _row_remove_button(self, slot) -> QPushButton:
        """Monochrome remove control matching the up/down row buttons."""
        c = colors_for(self._theme)
        button = QPushButton("×")
        button.setFixedSize(self._ACTION_BUTTON_SIZE, self._ACTION_BUTTON_SIZE)
        button.setToolTip("Remove from list")
        button.setStyleSheet(
            button_stylesheet(self._theme, "compact")
            + f"""
            QPushButton {{
                color: {c['muted']};
                font-size: 16px;
                font-weight: 500;
                padding: 0;
            }}
            QPushButton:hover {{
                color: {c['text']};
            }}
            """
        )
        button.clicked.connect(slot)
        return button

    def _action_cell_widget(self, widget: QWidget, right_pad: int = 0) -> QWidget:
        """Center row actions inside the cell; optional right gutter before scrollbar."""
        host = QWidget()
        host.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        layout = QHBoxLayout(host)
        layout.setContentsMargins(0, 0, right_pad, 0)
        layout.setSpacing(0)
        layout.addStretch(1)
        layout.addWidget(widget, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addStretch(1)
        return host

    @staticmethod
    def _display_release_date(comic: Comic) -> str:
        if comic.release_date is not None:
            return comic.release_date.strftime("%Y-%m-%d")
        if comic.year:
            return comic.year
        return "—"

    def _populate_table(self):
        self.table.setRowCount(len(self.reading_list.comics))
        last = len(self.reading_list.comics) - 1
        for row, comic in enumerate(self.reading_list.comics):
            up = self._row_icon_button(
                QStyle.StandardPixmap.SP_ArrowUp,
                "Move up",
                lambda _, r=row: self._move_up(r),
            )
            down = self._row_icon_button(
                QStyle.StandardPixmap.SP_ArrowDown,
                "Move down",
                lambda _, r=row: self._move_down(r),
            )
            up.setEnabled(row > 0)
            down.setEnabled(row < last)
            self.table.setCellWidget(row, 0, self._action_cell_widget(up))
            self.table.setCellWidget(
                row, 1, self._action_cell_widget(down, right_pad=2),
            )
            self.table.setItem(row, 2, QTableWidgetItem(str(row + 1)))
            series_label = comic.series_name or "—"
            series_item = QTableWidgetItem(series_label)
            if series_label != "—":
                series_item.setToolTip(series_label)
            self.table.setItem(row, self._COL_SERIES, series_item)
            self.table.setItem(row, self._COL_VOLUME, QTableWidgetItem(comic.volume or "—"))
            self.table.setItem(row, self._COL_ISSUE, QTableWidgetItem(comic.issue_number or "—"))
            title_label = comic.title or "—"
            title_item = QTableWidgetItem(title_label)
            if title_label != "—":
                title_item.setToolTip(title_label)
            self.table.setItem(row, self._COL_TITLE, title_item)
            self.table.setItem(
                row, self._COL_RELEASE, QTableWidgetItem(self._display_release_date(comic)),
            )
            file_name = Path(comic.path).name if comic.path else "—"
            file_item = QTableWidgetItem(file_name)
            if comic.path:
                file_item.setToolTip(str(comic.path))
            self.table.setItem(row, self._COL_FILE, file_item)
            remove = self._row_remove_button(lambda _, r=row: self._remove_at(r))
            self.table.setCellWidget(
                row,
                self._COL_REMOVE,
                self._action_cell_widget(remove, self._REMOVE_CELL_RIGHT_PAD),
            )
            self.table.setRowHeight(row, self._ROW_HEIGHT)
        self.sort_controls.set_order_state(self.reading_list.ordered_by == "manual")
        self._update_count()

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
        self._source_cbl_path = Path(path)
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

    def _move_up(self, row):
        if row > 0:
            previous = self._list_snapshot()
            self.reading_list.move_comic(self.reading_list.comics[row], -1)
            self._populate_table()
            self._update_preview()
            self._set_dirty(True)
            self._emit_list_changed_if_needed(previous)

    def _move_down(self, row):
        if row < len(self.reading_list.comics) - 1:
            previous = self._list_snapshot()
            self.reading_list.move_comic(self.reading_list.comics[row], 1)
            self._populate_table()
            self._update_preview()
            self._set_dirty(True)
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
