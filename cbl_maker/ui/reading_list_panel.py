"""Reading list panel with item reordering via table buttons."""

import logging
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QPushButton, QLabel, QMessageBox,
    QTextEdit, QFileDialog, QComboBox
)


from cbl_maker.models import Comic, ReadingList
from cbl_maker.services.cbl_writer import generate_cbl, save_cbl

logger = logging.getLogger(__name__)


class ReadingListPanel(QWidget):
    """Panel for managing the reading list."""

    def __init__(self):
        super().__init__()
        self.reading_list = ReadingList(name="New Reading List")
        self._setup_ui()

    def _setup_ui(self):
        """Set up the panel UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Header
        header = QWidget()
        header.setStyleSheet("""
            QWidget {
                background-color: #2b2b2b;
                border-bottom: 1px solid #3d3d3d;
            }
        """)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 12, 12, 12)
        
        label = QLabel("Reading List")
        label.setStyleSheet("""
            QLabel {
                color: #e0e0e0;
                font-size: 14px;
                font-weight: bold;
            }
        """)
        header_layout.addWidget(label)
        
        self.name_label = QLabel(self.reading_list.name)
        self.name_label.setStyleSheet("color: #808080; font-size: 12px;")
        header_layout.addWidget(self.name_label)

        # Sort selector
        sort_label = QLabel("Sort by:")
        sort_label.setStyleSheet("color: #808080; font-size: 12px; margin-left: 16px;")
        header_layout.addWidget(sort_label)

        self.sort_combo = QComboBox()
        self.sort_combo.addItems(["Manual", "Release Date", "Series + Issue", "Volume", "Title"])
        self.sort_combo.setStyleSheet("""
    QComboBox {
        background-color: #3d3d3d;
        color: #e0e0e0;
        border: 1px solid #4d4d4d;
        border-radius: 4px;
        padding: 4px 8px;
        min-width: 120px;
    }
    QComboBox:hover {
        background-color: #4d4d4d;
    }
    QComboBox::drop-down {
        border: none;
    }
    QComboBox QAbstractItemView {
        background-color: #2b2b2b;
        color: #e0e0e0;
        selection-background-color: #264f78;
        border: 1px solid #3d3d3d;
    }
""")
        self.sort_combo.currentIndexChanged.connect(self._on_sort_changed)
        header_layout.addWidget(self.sort_combo)

        header_layout.addStretch()
        
        layout.addWidget(header)
        
        # Table
        self._setup_table()
        layout.addWidget(self.table)
        
        # Bottom bar with count
        bottom_bar = QWidget()
        bottom_bar.setStyleSheet("""
            QWidget {
                background-color: #2b2b2b;
                border-top: 1px solid #3d3d3d;
            }
        """)
        bottom_bar_layout = QHBoxLayout(bottom_bar)
        bottom_bar_layout.setContentsMargins(8, 4, 8, 4)
        
        self.count_label = QLabel("0 items")
        self.count_label.setStyleSheet("color: #808080; font-size: 12px;")
        bottom_bar_layout.addWidget(self.count_label)
        bottom_bar_layout.addStretch()
        
        layout.addWidget(bottom_bar)
        
        # Preview label
        preview_label = QLabel("CBL Preview")
        preview_label.setStyleSheet("""
            QLabel {
                color: #808080;
                padding: 4px 12px;
                font-size: 11px;
                background-color: #2b2b2b;
                border-top: 1px solid #3d3d3d;
            }
        """)
        layout.addWidget(preview_label)
        
        # Preview
        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setMaximumHeight(120)
        self.preview.setPlaceholderText("CBL preview will appear here...")
        self.preview.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: none;
                border-top: 1px solid #3d3d3d;
                font-family: monospace;
                font-size: 11px;
                padding: 8px;
            }
        """)
        layout.addWidget(self.preview)
        
        # Export button
        export_bar = QWidget()
        export_bar.setStyleSheet("""
            QWidget {
                background-color: #2b2b2b;
                border-top: 1px solid #3d3d3d;
            }
        """)
        export_layout = QHBoxLayout(export_bar)
        export_layout.setContentsMargins(8, 8, 8, 8)
        
        self.export_btn = QPushButton("Export CBL")
        self.export_btn.setStyleSheet("""
            QPushButton {
                background-color: #0e639c;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1177bb;
            }
            QPushButton:pressed {
                background-color: #094771;
            }
            QPushButton:disabled {
                background-color: #3d3d3d;
                color: #6d6d6d;
            }
        """)
        self.export_btn.clicked.connect(self.export_cbl)
        export_layout.addWidget(self.export_btn)
        
        layout.addWidget(export_bar)

    def _setup_table(self):
        """Set up the table with comics."""
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["", "", "Comic", ""])
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #1e1e1e;
                color: #e0e0e0;
                border: none;
                gridline-color: #2d2d2d;
            }
            QTableWidget::item {
                padding: 4px;
            }
            QTableWidget::item:selected {
                background-color: #264f78;
            }
            QHeaderView::section {
                background-color: #2b2b2b;
                color: #808080;
                padding: 4px;
                border: none;
                border-right: 1px solid #3d3d3d;
                border-bottom: 1px solid #3d3d3d;
            }
        """)

    def _populate_table(self):
        """Populate table with comics from reading list."""
        self.table.setRowCount(0)
        self.table.setRowCount(len(self.reading_list.comics))
        
        for row, comic in enumerate(self.reading_list.comics):
            # Up button
            up_btn = QPushButton("▲")
            up_btn.setFixedSize(24, 24)
            up_btn.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    color: #808080;
                    border: none;
                    border-radius: 4px;
                    font-size: 11px;
                }
                QPushButton:hover {
                    background-color: #3d3d3d;
                    color: #e0e0e0;
                }
            """)
            up_btn.clicked.connect(lambda _, r=row: self._move_up(r))
            self.table.setCellWidget(row, 0, up_btn)
            
            # Down button
            down_btn = QPushButton("▼")
            down_btn.setFixedSize(24, 24)
            down_btn.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    color: #808080;
                    border: none;
                    border-radius: 4px;
                    font-size: 11px;
                }
                QPushButton:hover {
                    background-color: #3d3d3d;
                    color: #e0e0e0;
                }
            """)
            down_btn.clicked.connect(lambda _, r=row: self._move_down(r))
            self.table.setCellWidget(row, 1, down_btn)
            
            # Comic info
            display_name = comic.title if comic.title else comic.series_name
            year = f" ({comic.year})" if comic.year else ""
            item = QTableWidgetItem(f"{display_name} #{comic.issue_number}{year}")
            self.table.setItem(row, 2, item)
            
            # Delete button
            del_btn = QPushButton("×")
            del_btn.setFixedSize(24, 24)
            del_btn.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    color: #808080;
                    border: none;
                    border-radius: 4px;
                    font-size: 14px;
                }
                QPushButton:hover {
                    background-color: #c42b1c;
                    color: #e0e0e0;
                }
            """)
            del_btn.clicked.connect(lambda _, r=row: self._remove_at(r))
            self.table.setCellWidget(row, 3, del_btn)
        
        self._update_count()

    def _update_count(self):
        """Update item count label."""
        count = len(self.reading_list.comics)
        self.count_label.setText(f"{count} item{'s' if count != 1 else ''}")

    def _on_sort_changed(self, index):
        """Handle sort criteria change."""
        criteria = ["manual", "release_date", "series_issue", "volume", "title"]
        criterion = criteria[index]
        self.reading_list.sort_by(criterion)
        self._populate_table()
        self._update_preview()

    def add_comic(self, comic: Comic):
        """Add a comic to the reading list."""
        if self.reading_list.add_comic(comic):
            self._populate_table()
            self._update_preview()
        else:
            QMessageBox.information(
                self, "Duplicate",
                "This comic is already in the list"
            )

    def _move_up(self, row):
        """Move item up."""
        if row > 0:
            comic = self.reading_list.comics[row]
            self.reading_list.comics.pop(row)
            self.reading_list.comics.insert(row - 1, comic)
            self._populate_table()
            self._update_preview()

    def _move_down(self, row):
        """Move item down."""
        if row < len(self.reading_list.comics) - 1:
            comic = self.reading_list.comics[row]
            self.reading_list.comics.pop(row)
            self.reading_list.comics.insert(row + 1, comic)
            self._populate_table()
            self._update_preview()

    def _remove_at(self, row):
        """Remove item at row."""
        if 0 <= row < len(self.reading_list.comics):
            self.reading_list.comics.pop(row)
            self._populate_table()
            self._update_preview()

    def _update_preview(self):
        """Update the XML preview."""
        if self.reading_list.comics:
            xml = generate_cbl(self.reading_list)
            self.preview.setPlainText(xml)
        else:
            self.preview.clear()

    def export_cbl(self):
        """Export reading list as CBL file."""
        if not self.reading_list.comics:
            QMessageBox.warning(self, "Error", "Reading list is empty")
            return
        
        # Use current list name as default filename
        default_name = self.reading_list.name.replace(" ", "_")
        
        path, _ = QFileDialog.getSaveFileName(
            self, "Save CBL File",
            f"{default_name}.cbl",
            "CBL Files (*.cbl);;All Files (*)"
        )
        if path:
            xml = generate_cbl(self.reading_list)
            save_cbl(xml, Path(path))
            QMessageBox.information(
                self, "Success",
                f"Reading list saved to:\n{path}"
            )
