"""Reading list panel with item reordering and export controls."""

import logging
import re
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog, QHeaderView, QMessageBox, QPushButton, QSplitter,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from cbl_maker.models import Comic, ReadingList
from cbl_maker.services.cbl_writer import generate_cbl, save_cbl
from cbl_maker.ui.reading_list_header import ReadingListHeader
from cbl_maker.ui.reading_list_sort import ReadingListSort
from cbl_maker.ui.cbl_preview import CBLPreview

logger = logging.getLogger(__name__)

_WINDOWS_RESERVED_FILENAME = re.compile(
    r"^(?:con|prn|aux|nul|clock\$|com[1-9]|lpt[1-9])(?:\..*)?$",
    re.IGNORECASE,
)


class ReadingListPanel(QWidget):
    """Panel for managing the reading list."""

    status_message = Signal(str)
    dirty_changed = Signal(bool)

    def __init__(self):
        super().__init__()
        self.reading_list = ReadingList(name="New Reading List")
        self.is_dirty = False
        self._setup_ui()
        self._populate_table()
        self._update_preview()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.header = ReadingListHeader(self.reading_list)
        # Compatibility aliases retained for callers of the previous panel API.
        self.name_label = self.header.name_edit
        self.count_label = self.header.count_label
        self.clear_btn = self.header.clear_btn
        self.export_btn = self.header.export_btn
        self.export_btn.setObjectName("primaryExportButton")
        self.export_btn.setDefault(True)
        self.header.clear_requested.connect(self.clear_list)
        self.header.export_requested.connect(self.export_cbl)
        self.header.name_changed.connect(self._on_name_changed)
        layout.addWidget(self.header)

        controls = QWidget()
        controls_layout = QVBoxLayout(controls)
        controls_layout.setContentsMargins(12, 6, 12, 6)
        sort_row = ReadingListSort()
        sort_row.changed.connect(self._on_sort_changed)
        # Keep the old attribute as an API alias, while exposing explicit controls.
        self.sort_controls = sort_row
        self.sort_combo = sort_row.criterion_combo
        self.direction_combo = sort_row.direction_combo
        self.sort_direction_combo = sort_row.direction_combo
        self.manual_check = sort_row.manual_check
        controls_layout.addWidget(sort_row)
        layout.addWidget(controls)

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
            display = comic.title or comic.series_name
            year = f" ({comic.year})" if comic.year else ""
            self.table.setItem(row, 2, QTableWidgetItem(f"{display} #{comic.issue_number}{year}"))
            self.table.setCellWidget(row, 3, self._button("×", lambda _, r=row: self._remove_at(r)))
        self._update_count()

    def _update_count(self):
        self.header.set_count(len(self.reading_list.comics))

    def _on_sort_changed(self, index):
        if self.sort_controls.is_manual:
            self.reading_list.sort_by("manual")
        else:
            self.reading_list.sort_by(
                self.sort_combo.currentData(), self.direction_combo.currentData()
            )
        self._populate_table()
        self._update_preview()
        self._set_dirty(True)

    def _on_name_changed(self, _name):
        self._update_preview()
        self._set_dirty(True)

    def _set_dirty(self, dirty):
        """Track edits so the host window can expose unsaved changes."""
        dirty = bool(dirty)
        if self.is_dirty != dirty:
            self.is_dirty = dirty
            self.dirty_changed.emit(dirty)

    def add_comic(self, comic: Comic):
        if self.reading_list.add_comic(comic):
            self._apply_current_order()
            self._populate_table()
            self._update_preview()
            self._set_dirty(True)
        else:
            QMessageBox.information(self, "Duplicate", "This comic is already in the list")

    def _move_up(self, row):
        if self.reading_list.ordered_by == "manual" and row > 0:
            self.reading_list.move_comic(self.reading_list.comics[row], -1)
            self._populate_table(); self._update_preview(); self._set_dirty(True)

    def _move_down(self, row):
        if self.reading_list.ordered_by == "manual" and row < len(self.reading_list.comics) - 1:
            self.reading_list.move_comic(self.reading_list.comics[row], 1)
            self._populate_table(); self._update_preview(); self._set_dirty(True)

    def _remove_at(self, row):
        if 0 <= row < len(self.reading_list.comics):
            self.reading_list.comics.pop(row)
            self._populate_table(); self._update_preview(); self._set_dirty(True)

    def clear_list(self):
        """Remove all comics and refresh action states."""
        if not self.reading_list.comics:
            return
        self.reading_list.comics.clear()
        self._populate_table()
        self._update_preview()
        self._set_dirty(True)

    def _apply_current_order(self):
        """Reapply the selected order without ever changing manual order."""
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
        path, _ = QFileDialog.getSaveFileName(
            self, "Save CBL File", f"{default_name}.cbl",
            "CBL Files (*.cbl);;All Files (*)",
        )
        if path:
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
        """Turn a user-facing list name into a safe, portable filename stem."""
        value = (name or "").strip()
        # Separators must be handled explicitly so a list name can never create
        # another path component when it is used as the dialog's default name.
        value = re.sub(r"[\\/]", "_", value)
        stem = re.sub(r"[^\w.-]+", "_", value, flags=re.UNICODE)
        stem = re.sub(r"_+", "_", stem).strip("._")
        if not stem:
            return "reading_list"

        # Windows reserves these device names even when an extension follows
        # them (the export code appends .cbl to this stem).
        if _WINDOWS_RESERVED_FILENAME.match(stem):
            stem = f"_{stem}"
        return stem
