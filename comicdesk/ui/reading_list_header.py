"""Header controls for the current reading list."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from comicdesk.ui.layout.breakpoints import is_action_bar_compact
from comicdesk.ui.theme import (
    button_stylesheet,
    colors_for,
    menu_stylesheet,
    muted_label_stylesheet,
    panel_header_stylesheet,
)


class ReadingListHeader(QWidget):
    """Editable list identity and list-level actions."""

    name_changed = Signal(str)
    clear_requested = Signal()
    export_requested = Signal()
    import_requested = Signal()
    save_requested = Signal()

    def __init__(self, reading_list, parent=None):
        super().__init__(parent)
        self.reading_list = reading_list
        self._original_name = reading_list.name
        self._theme = "dark"
        self.setObjectName("readingListHeader")

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 8)
        root.setSpacing(6)

        row1 = QHBoxLayout()
        self.name_edit = QLineEdit(reading_list.name)
        self.name_edit.setPlaceholderText("List name")
        self.name_edit.editingFinished.connect(self.commit_name)
        row1.addWidget(self.name_edit, 1)
        self.cancel_name_btn = QPushButton("Cancel")
        self.cancel_name_btn.clicked.connect(self.cancel_name_edit)
        row1.addWidget(self.cancel_name_btn)
        self.count_label = QLabel("0 items")
        row1.addWidget(self.count_label)
        self.dirty_label = QLabel("")
        row1.addWidget(self.dirty_label)
        root.addLayout(row1)

        row2 = QHBoxLayout()
        self.import_btn = QPushButton("Import CBL")
        self.import_btn.clicked.connect(self.import_requested)
        self.save_btn = QPushButton("Save")
        self.save_btn.setToolTip("Save to the imported CBL file, or choose a path if none was imported")
        self.save_btn.clicked.connect(self.save_requested)
        self.export_btn = QPushButton("Export CBL")
        self.export_btn.setToolTip("Save the list to a new CBL file")
        self.export_btn.clicked.connect(self.export_requested)
        self.clear_btn = QPushButton("Clear list")
        self.clear_btn.clicked.connect(self.clear_requested)
        self.more_btn = QToolButton()
        self.more_btn.setText("More")
        self.more_btn.setPopupMode(QToolButton.InstantPopup)
        row2.addWidget(self.import_btn)
        row2.addWidget(self.export_btn)
        row2.addWidget(self.clear_btn)
        row2.addWidget(self.save_btn)
        row2.addWidget(self.more_btn)
        row2.addStretch()
        root.addLayout(row2)

        self.title_label = QLabel("Reading list")
        self.title_label.hide()
        self.apply_theme(self._theme)

    def set_dirty(self, dirty: bool) -> None:
        self.dirty_label.setText("Unsaved changes" if dirty else "")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        compact = is_action_bar_compact(self.width())
        menu = QMenu(self)
        menu.setStyleSheet(menu_stylesheet(self._theme))
        if compact:
            self.import_btn.hide()
            self.export_btn.hide()
            self.clear_btn.hide()
            menu.addAction("Import CBL", self.import_btn.click)
            menu.addAction("Export CBL", self.export_btn.click)
            menu.addAction("Clear list", self.clear_btn.click)
            self.more_btn.setMenu(menu)
            self.more_btn.show()
        else:
            self.import_btn.show()
            self.export_btn.show()
            self.clear_btn.show()
            self.save_btn.show()
            self.more_btn.setMenu(None)
            self.more_btn.hide()

    def apply_theme(self, theme: str) -> None:
        self._theme = theme
        c = colors_for(theme)
        self.setStyleSheet(f"#readingListHeader {{ {panel_header_stylesheet(theme)} }}")
        self.name_edit.setStyleSheet(
            f"QLineEdit {{ color: {c['text']}; background: {c['input_bg']};"
            f" border: 1px solid {c['border_strong']}; border-radius: 4px; padding: 4px 6px; }}"
        )
        self.count_label.setStyleSheet(muted_label_stylesheet(theme))
        self.dirty_label.setStyleSheet(
            f"color: {c['accent']}; font-size: 12px; font-weight: 600;"
        )
        default_btn = button_stylesheet(theme, "default")
        self.cancel_name_btn.setStyleSheet(default_btn)
        self.import_btn.setStyleSheet(default_btn)
        self.clear_btn.setStyleSheet(default_btn)
        self.export_btn.setStyleSheet(default_btn)
        self.save_btn.setStyleSheet(button_stylesheet(theme, "primary"))

    def commit_name(self):
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
        self.name_edit.setText(self._original_name)
        self.name_edit.clearFocus()

    def set_count(self, count):
        self.count_label.setText(f"{count} item{'s' if count != 1 else ''}")
        self.clear_btn.setEnabled(count > 0)
        self.save_btn.setEnabled(count > 0)
        self.export_btn.setEnabled(count > 0)

    def set_reading_list(self, reading_list):
        self.reading_list = reading_list
        self._original_name = reading_list.name
        self.name_edit.setText(reading_list.name)
