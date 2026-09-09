"""Search and filtering toolbar for the comic list."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QLineEdit, QWidget

from comicdesk.ui.theme import colors_for, muted_label_stylesheet


class ComicListToolbar(QWidget):
    """Toolbar whose state is transient and communicated through signals."""

    query_changed = Signal(str)
    status_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._theme = "dark"
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search file, series or title…")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self.query_changed.emit)
        layout.addWidget(self.search_edit, 1)

        self.status_caption = QLabel("Status:")
        layout.addWidget(self.status_caption)
        self.status_combo = QComboBox()
        self.status_combo.addItem("All", "all")
        self.status_combo.addItem("Enriched", "enriched")
        self.status_combo.addItem("Partial", "partial")
        self.status_combo.addItem("Pending", "pending")
        self.status_combo.currentIndexChanged.connect(
            lambda index: self.status_changed.emit(self.status_combo.itemData(index)))
        layout.addWidget(self.status_combo)

        # Descriptive aliases keep the toolbar convenient for callers and tests.
        self.search_input = self.search_edit
        self.filter_combo = self.status_combo

        self.results_label = QLabel("0 results · 0 selected")
        self.results_label.setMinimumWidth(150)
        layout.addWidget(self.results_label)
        self.apply_theme(self._theme)

    def apply_theme(self, theme: str) -> None:
        """Re-apply visual tokens for the active theme."""
        self._theme = theme
        c = colors_for(theme)
        self.setStyleSheet(
            f"background-color: {c['canvas']}; color: {c['text']};"
        )
        self.status_caption.setStyleSheet(f"color: {c['text']};")
        self.results_label.setStyleSheet(muted_label_stylesheet(theme))

    def set_counts(self, results, selected):
        self.results_label.setText(f"{results} results · {selected} selected")
