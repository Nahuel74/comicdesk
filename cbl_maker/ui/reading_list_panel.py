"""Reading list panel with drag and drop support."""

from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListView,
    QPushButton, QLabel, QInputDialog, QMessageBox,
    QTextEdit, QFileDialog
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
        
        # Header
        header_layout = QHBoxLayout()
        label = QLabel("Reading List")
        label.setStyleSheet("font-weight: bold;")
        header_layout.addWidget(label)
        
        self.name_label = QLabel(self.reading_list.name)
        header_layout.addWidget(self.name_label)
        header_layout.addStretch()
        
        layout.addLayout(header_layout)
        
        # List view
        self.model = ReadingListModel(self.reading_list)
        self.list_view = QListView()
        self.list_view.setModel(self.model)
        self.list_view.setDragDropMode(QListView.InternalMove)
        layout.addWidget(self.list_view)
        
        # Preview
        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setMaximumHeight(150)
        self.preview.setPlaceholderText("CBL preview will appear here...")
        layout.addWidget(self.preview)
        
        # Buttons
        btn_layout = QHBoxLayout()
        
        self.up_btn = QPushButton("↑ Up")
        self.up_btn.clicked.connect(self._move_up)
        btn_layout.addWidget(self.up_btn)
        
        self.down_btn = QPushButton("↓ Down")
        self.down_btn.clicked.connect(self._move_down)
        btn_layout.addWidget(self.down_btn)
        
        self.remove_btn = QPushButton("Remove")
        self.remove_btn.clicked.connect(self._remove_selected)
        btn_layout.addWidget(self.remove_btn)
        
        btn_layout.addStretch()
        
        self.export_btn = QPushButton("Export CBL")
        self.export_btn.clicked.connect(self.export_cbl)
        btn_layout.addWidget(self.export_btn)
        
        layout.addLayout(btn_layout)

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
        
        # Get list name
        name, ok = QInputDialog.getText(
            self, "Reading List Name",
            "Enter name for the reading list:",
            text=self.reading_list.name
        )
        if not ok or not name:
            return
        
        self.reading_list.name = name
        self.name_label.setText(name)
        
        # Get save location
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
