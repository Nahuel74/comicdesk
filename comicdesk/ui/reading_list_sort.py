"""Explicit sorting controls for a reading list."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPushButton, QWidget

from comicdesk.ui.theme import button_stylesheet, colors_for, muted_label_stylesheet


class ReadingListSort(QWidget):
    """Criterion and direction; sorting runs when the user clicks Apply."""

    apply_requested = Signal()
    remove_requested = Signal()

    CRITERIA = (
        ("release_date", "Release Date"),
        ("series_issue", "Series + Issue"),
        ("volume", "Volume"),
        ("title", "Title"),
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self._theme = "dark"
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.order_label = QLabel("Order by:")
        layout.addWidget(self.order_label)
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
        self.apply_button = QPushButton("Apply")
        self.apply_button.setToolTip("Sort the list using the selected criterion")
        self.apply_button.setFixedHeight(28)
        self.apply_button.clicked.connect(self.apply_requested.emit)
        layout.addWidget(self.apply_button)
        self.state_label = QLabel("Sorted")
        layout.addWidget(self.state_label)
        self.reorder_hint = QLabel("Drag rows to reorder (custom order).")
        layout.addWidget(self.reorder_hint)
        self.remove_button = QPushButton("Remove")
        self.remove_button.setToolTip("Remove selected row from the list")
        self.remove_button.setFixedHeight(28)
        self.remove_button.clicked.connect(self.remove_requested.emit)
        layout.addWidget(self.remove_button)
        layout.addStretch(1)
        self.apply_theme(self._theme)

    def apply_theme(self, theme: str) -> None:
        """Re-apply visual tokens for the active theme."""
        self._theme = theme
        c = colors_for(theme)
        self.setStyleSheet(f"color: {c['text']};")
        self.order_label.setStyleSheet(f"color: {c['text']};")
        self.state_label.setStyleSheet(muted_label_stylesheet(theme))
        self.reorder_hint.setStyleSheet(muted_label_stylesheet(theme, size=11))
        compact = button_stylesheet(theme, "compact")
        self.apply_button.setStyleSheet(compact)
        self.remove_button.setStyleSheet(compact)

    @property
    def criterion(self):
        return self.criterion_combo.currentData()

    @property
    def direction(self):
        return self.direction_combo.currentData()

    def set_order_state(self, manual: bool) -> None:
        self.state_label.setText("Custom order" if manual else "Sorted")
        self.reorder_hint.setVisible(manual)

    def set_reorder_enabled(self, enabled: bool) -> None:
        self.remove_button.setEnabled(enabled)
