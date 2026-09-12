"""Animated wrapper around the folder sidebar."""

from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, Signal
from PySide6.QtWidgets import QSizePolicy, QVBoxLayout, QWidget

from comicdesk.ui.folder_panel import FolderPanel

COLLAPSED_WIDTH = 48
EXPANDED_MIN_WIDTH = 200
EXPANDED_DEFAULT_WIDTH = 240


class CollapsibleSidebar(QWidget):
    """Hosts :class:`FolderPanel` with smooth width animation."""

    folder_selected = Signal(object)
    collapsed_changed = Signal(bool)

    def __init__(self, default_folder: str = "", parent=None):
        super().__init__(parent)
        self._expanded_width = EXPANDED_DEFAULT_WIDTH
        self._collapsed = False
        self._animating_width = EXPANDED_DEFAULT_WIDTH

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.folder_panel = FolderPanel(default_folder=default_folder)
        self.folder_panel.folder_selected.connect(self.folder_selected.emit)
        self.folder_panel.collapsed_changed.connect(self._on_panel_collapsed)
        layout.addWidget(self.folder_panel)

        self.setMinimumWidth(EXPANDED_MIN_WIDTH)
        self.setMaximumWidth(EXPANDED_DEFAULT_WIDTH)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

        self._animation = QPropertyAnimation(self, b"animatingWidth", self)
        self._animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._animation.setDuration(180)

    def get_animating_width(self) -> int:
        return self._animating_width

    def set_animating_width(self, value: int) -> None:
        self._animating_width = value
        self.setFixedWidth(int(value))

    animatingWidth = Property(int, get_animating_width, set_animating_width)

    @property
    def collapsed(self) -> bool:
        return self._collapsed

    def toggle_collapsed(self) -> None:
        """Collapse or expand the sidebar (menu shortcut target)."""
        self.folder_panel.toggle_collapsed()

    def _on_panel_collapsed(self, collapsed: bool) -> None:
        self._collapsed = collapsed
        if collapsed:
            self._expanded_width = max(self.width(), self._expanded_width)
            self._animate_to(COLLAPSED_WIDTH)
        else:
            target = max(self._expanded_width, EXPANDED_MIN_WIDTH)
            self._animate_to(target)
        self.collapsed_changed.emit(collapsed)

    def _animate_to(self, target: int) -> None:
        self._animation.stop()
        self._animation.setStartValue(self.width())
        self._animation.setEndValue(target)
        self._animation.start()

    def set_default_folder(self, folder: str) -> None:
        self.folder_panel.set_default_folder(folder)

    def select_folder(self, path) -> None:
        self.folder_panel.select_folder(path)

    def restore_visible_width(self) -> None:
        """Ensure the sidebar has a usable width after being re-shown."""
        target = COLLAPSED_WIDTH if self._collapsed else max(
            self._expanded_width, EXPANDED_MIN_WIDTH
        )
        self.set_animating_width(target)

    def apply_theme(self, theme: str) -> None:
        self.folder_panel.apply_theme(theme)
