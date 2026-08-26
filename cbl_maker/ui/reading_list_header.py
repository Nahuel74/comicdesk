"""Header controls for the current reading list."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QPushButton, QWidget


class ReadingListHeader(QWidget):
    """Editable list identity and list-level actions."""

    name_changed = Signal(str)
    clear_requested = Signal()
    export_requested = Signal()
    import_requested = Signal()

    def __init__(self, reading_list, parent=None):
        super().__init__(parent)
        self.reading_list = reading_list
        self._original_name = reading_list.name
        self.setObjectName("readingListHeader")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        title = QLabel("Reading List")
        title.setStyleSheet("color: #e0e0e0; font-size: 14px; font-weight: bold;")
        layout.addWidget(title)
        self.name_edit = QLineEdit(reading_list.name)
        self.name_edit.setPlaceholderText("List name")
        self.name_edit.setToolTip("Enter a name for the reading list")
        self.name_edit.setMinimumWidth(130)
        self.name_edit.setStyleSheet(
            "QLineEdit { color: #e0e0e0; background: #3d3d3d; border: 1px solid #4d4d4d;"
            " border-radius: 4px; padding: 4px 6px; }"
        )
        self.name_edit.editingFinished.connect(self.commit_name)
        layout.addWidget(self.name_edit)
        self.cancel_name_btn = QPushButton("✕")
        self.cancel_name_btn.setToolTip("Cancel name edit")
        self.cancel_name_btn.setFixedWidth(26)
        self.cancel_name_btn.clicked.connect(self.cancel_name_edit)
        layout.addWidget(self.cancel_name_btn)
        layout.addStretch()

        self.count_label = QLabel("0 items")
        self.count_label.setStyleSheet("color: #808080; font-size: 12px;")
        layout.addWidget(self.count_label)
        self.clear_btn = QPushButton("Clear")
        self.clear_btn.setToolTip("Remove all comics from the list")
        self.clear_btn.clicked.connect(self.clear_requested)
        layout.addWidget(self.clear_btn)
        self.import_btn = QPushButton("Import CBL")
        self.import_btn.setToolTip("Import and update the reading list from a CBL file")
        self.import_btn.clicked.connect(self.import_requested)
        layout.addWidget(self.import_btn)
        self.export_btn = QPushButton("Export CBL")
        self.export_btn.setToolTip("Export this reading list")
        self.export_btn.clicked.connect(self.export_requested)
        layout.addWidget(self.export_btn)
        self.setStyleSheet("#readingListHeader { background: #2b2b2b; border-bottom: 1px solid #3d3d3d; }")

    def commit_name(self):
        """Commit a non-empty name, otherwise restore the previous value."""
        name = self.name_edit.text().strip()
        if not name:
            self.name_edit.setText(self._original_name)
            self.name_edit.setFocus()
            return False
        changed = name != self._original_name
        self.reading_list.name = name
        self._original_name = name
        self.name_edit.setText(name)
        if changed:
            self.name_changed.emit(name)
        return True

    def cancel_name_edit(self):
        """Restore the last committed name without changing the model."""
        self.name_edit.setText(self._original_name)
        self.name_edit.clearFocus()

    def set_count(self, count):
        self.count_label.setText(f"{count} item{'s' if count != 1 else ''}")
        self.clear_btn.setEnabled(count > 0)
        self.export_btn.setEnabled(count > 0)

    def set_reading_list(self, reading_list):
        """Point the header at a newly imported list without emitting edits."""
        self.reading_list = reading_list
        self._original_name = reading_list.name
        self.name_edit.setText(reading_list.name)
