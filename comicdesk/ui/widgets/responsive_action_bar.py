"""Toolbar that moves actions into an overflow menu on narrow widths."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QMenu, QToolButton, QWidget

from comicdesk.ui.layout.breakpoints import is_action_bar_compact
from comicdesk.ui.theme import menu_stylesheet, SPACING


class ResponsiveActionBar(QWidget):
    """Host primary actions inline; overflow into a menu when space is tight."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._theme = "dark"
        self._actions: list[tuple[QWidget, str]] = []
        self._inline_layout = QHBoxLayout()
        self._inline_layout.setContentsMargins(0, 0, 0, 0)
        self._inline_layout.setSpacing(SPACING["sm"])

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(SPACING["sm"])
        root.addLayout(self._inline_layout, 1)

        self._overflow_btn = QToolButton()
        self._overflow_btn.setText("⋯")
        self._overflow_btn.setToolTip("More actions")
        self._overflow_btn.setPopupMode(QToolButton.InstantPopup)
        self._overflow_btn.hide()
        root.addWidget(self._overflow_btn)

    def add_action(self, widget: QWidget, menu_label: str | None = None) -> None:
        label = menu_label or widget.toolTip() or widget.text()
        self._actions.append((widget, label))
        self._inline_layout.addWidget(widget)
        self._relayout_overflow()

    def apply_theme(self, theme: str) -> None:
        self._theme = theme

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._relayout_overflow()

    def _relayout_overflow(self) -> None:
        compact = is_action_bar_compact(self.width())
        menu = QMenu(self)
        menu.setStyleSheet(menu_stylesheet(self._theme))
        for widget, label in self._actions:
            if compact:
                widget.hide()
                action = menu.addAction(label)
                action.triggered.connect(widget.click)
            else:
                widget.show()
        if compact and self._actions:
            self._overflow_btn.setMenu(menu)
            self._overflow_btn.show()
        else:
            self._overflow_btn.setMenu(None)
            self._overflow_btn.hide()
