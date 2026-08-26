"""Explicit sorting controls for a reading list."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QComboBox, QHBoxLayout, QLabel, QWidget


class ReadingListSort(QWidget):
    """Criterion, direction, and independent manual-mode controls."""

    changed = Signal()

    CRITERIA = (
        ("release_date", "Release Date"),
        ("series_issue", "Series + Issue"),
        ("volume", "Volume"),
        ("title", "Title"),
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel("Order by:"))
        self.criterion_combo = QComboBox()
        for value, label in self.CRITERIA:
            self.criterion_combo.addItem(label, value)
        self.criterion_combo.setToolTip("Choose the ordering criterion")
        layout.addWidget(self.criterion_combo)
        self.direction_combo = QComboBox()
        self.direction_combo.addItem("Ascending", "asc")
        self.direction_combo.addItem("Descending", "desc")
        self.direction_combo.setToolTip("Choose the ordering direction")
        layout.addWidget(self.direction_combo)
        self.manual_check = QCheckBox("Manual")
        self.manual_check.setToolTip("Keep the current order and enable moving comics")
        layout.addWidget(self.manual_check)
        self.state_label = QLabel("Sorted")
        layout.addWidget(self.state_label)
        self.criterion_combo.currentIndexChanged.connect(self._sorted_changed)
        self.direction_combo.currentIndexChanged.connect(self._sorted_changed)
        self.manual_check.toggled.connect(self._manual_changed)

    @property
    def criterion(self):
        return self.criterion_combo.currentData()

    @property
    def direction(self):
        return self.direction_combo.currentData()

    @property
    def is_manual(self):
        return self.manual_check.isChecked()

    def set_manual(self, manual: bool):
        self.manual_check.setChecked(manual)

    def _sorted_changed(self, _index):
        if not self.is_manual:
            self.state_label.setText("Sorted")
            self.changed.emit()

    def _manual_changed(self, manual: bool):
        self.criterion_combo.setEnabled(not manual)
        self.direction_combo.setEnabled(not manual)
        self.state_label.setText("Manual order" if manual else "Sorted")
        self.changed.emit()
