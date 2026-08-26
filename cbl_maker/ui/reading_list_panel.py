"""Reading list panel with drag and drop support."""

from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListView,
    QPushButton, QLabel, QInputDialog, QMessageBox,
    QTextEdit, QFileDialog, QSizePolicy
)
from PySide6.QtCore import Signal, Qt, QAbstractListModel, QModelIndex
from PySide6.QtGui import QDrag

from cbl_maker.models import Comic, ReadingList
from cbl_maker.services.cbl_writer import generate_cbl, save_cbl


class ReadingListModel(QAbstractListModel):
    """Model for reading list items."""

    def __init__(self, reading_list: ReadingList):
        super().__init__()
        self.reading_list = reading_list

    def rowCount(self, parent=QModelIndex()):
        return len(self.reading_list.comics)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self.reading_list.comics):
            return None
        
        comic = self.reading_list.comics[index.row()]
        
        if role == Qt.DisplayRole:
            return f"{comic.series_name} #{comic.issue_number} ({comic.volume})"
        elif role == Qt.UserRole:
            return comic
        
        return None

    def move_up(self, row):
        if row > 0:
            comic = self.reading_list.comics[row]
            self.reading_list.move_comic(comic, -1)
            self.layoutChanged.emit()

    def move_down(self, row):
        if row < len(self.reading_list.comics) - 1:
            comic = self.reading_list.comics[row]
            self.reading_list.move_comic(comic, 1)
            self.layoutChanged.emit()

    def remove(self, row):
        if 0 <= row < len(self.reading_list.comics):
            comic = self.reading_list.comics[row]
            self.reading_list.remove_comic(comic)
            self.layoutChanged.emit()


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
        
        header_layout.addStretch()
        
        layout.addWidget(header)
        
        # List view
        self.model = ReadingListModel(self.reading_list)
        self.list_view = QListView()
        self.list_view.setModel(self.model)
        self.list_view.setDragDropMode(QListView.InternalMove)
        self.list_view.setStyleSheet("""
            QListView {
                background-color: #1e1e1e;
                color: #e0e0e0;
                border: none;
                outline: none;
            }
            QListView::item {
                padding: 8px 12px;
                min-height: 32px;
            }
            QListView::item:selected {
                background-color: #264f78;
            }
            QListView::item:hover:!selected {
                background-color: #2d2d2d;
            }
        """)
        layout.addWidget(self.list_view)
        
        # Buttons
        btn_bar = QWidget()
        btn_bar.setStyleSheet("""
            QWidget {
                background-color: #2b2b2b;
                border-top: 1px solid #3d3d3d;
                border-bottom: 1px solid #3d3d3d;
            }
        """)
        btn_layout = QHBoxLayout(btn_bar)
        btn_layout.setContentsMargins(8, 8, 8, 8)
        
        self.up_btn = QPushButton("⬆")
        self.up_btn.setFixedSize(32, 32)
        self.up_btn.setStyleSheet("""
            QPushButton {
                background-color: #3d3d3d;
                color: #e0e0e0;
                border: none;
                border-radius: 4px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #4d4d4d;
            }
        """)
        self.up_btn.clicked.connect(self._move_up)
        btn_layout.addWidget(self.up_btn)
        
        self.down_btn = QPushButton("⬇")
        self.down_btn.setFixedSize(32, 32)
        self.down_btn.setStyleSheet("""
            QPushButton {
                background-color: #3d3d3d;
                color: #e0e0e0;
                border: none;
                border-radius: 4px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #4d4d4d;
            }
        """)
        self.down_btn.clicked.connect(self._move_down)
        btn_layout.addWidget(self.down_btn)
        
        self.remove_btn = QPushButton("🗑")
        self.remove_btn.setFixedSize(32, 32)
        self.remove_btn.setStyleSheet("""
            QPushButton {
                background-color: #3d3d3d;
                color: #e0e0e0;
                border: none;
                border-radius: 4px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #c42b1c;
            }
        """)
        self.remove_btn.clicked.connect(self._remove_selected)
        btn_layout.addWidget(self.remove_btn)
        
        btn_layout.addStretch()
        
        layout.addWidget(btn_bar)
        
        # Preview
        preview_container = QWidget()
        preview_container.setStyleSheet("""
            QWidget {
                background-color: #1e1e1e;
            }
        """)
        preview_layout = QVBoxLayout(preview_container)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        
        preview_label = QLabel("CBL Preview")
        preview_label.setStyleSheet("""
            QLabel {
                color: #808080;
                padding: 8px 12px;
                font-size: 11px;
                background-color: #2b2b2b;
                border-top: 1px solid #3d3d3d;
            }
        """)
        preview_layout.addWidget(preview_label)
        
        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setMaximumHeight(120)
        self.preview.setPlaceholderText("CBL preview will appear here...")
        self.preview.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: none;
                font-family: monospace;
                font-size: 11px;
                padding: 8px;
            }
        """)
        preview_layout.addWidget(self.preview)
        
        layout.addWidget(preview_container)
        
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

    def add_comic(self, comic: Comic):
        """Add a comic to the reading list."""
        if self.reading_list.add_comic(comic):
            self.model.layoutChanged.emit()
            self._update_preview()
        else:
            QMessageBox.information(
                self, "Duplicate",
                "This comic is already in the list"
            )

    def _move_up(self):
        """Move selected item up."""
        row = self.list_view.currentIndex().row()
        if row >= 0:
            self.model.move_up(row)
            self._update_preview()

    def _move_down(self):
        """Move selected item down."""
        row = self.list_view.currentIndex().row()
        if row >= 0:
            self.model.move_down(row)
            self._update_preview()

    def _remove_selected(self):
        """Remove selected item."""
        row = self.list_view.currentIndex().row()
        if row >= 0:
            self.model.remove(row)
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
        
        name, ok = QInputDialog.getText(
            self, "Reading List Name",
            "Enter name for the reading list:",
            text=self.reading_list.name
        )
        if not ok or not name:
            return
        
        self.reading_list.name = name
        self.name_label.setText(name)
        
        path, _ = QFileDialog.getSaveFileName(
            self, "Save CBL File",
            f"{name}.cbl",
            "CBL Files (*.cbl);;All Files (*)"
        )
        if path:
            xml = generate_cbl(self.reading_list)
            save_cbl(xml, Path(path))
            QMessageBox.information(
                self, "Success",
                f"Reading list saved to:\n{path}"
            )
