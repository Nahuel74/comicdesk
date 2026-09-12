"""Primary workflow navigation across the app shell."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QLabel, QToolButton, QWidget

from comicdesk.ui.layout.breakpoints import is_nav_compact
from comicdesk.ui.theme import SPACING

NAV_LIBRARY = "library"
NAV_METADATA = "metadata"
NAV_LISTS = "lists"
NAV_ACQUIRE = "acquire"

_NAV_ITEMS = (
    (NAV_LIBRARY, "Library", "Browse CBZ folders and enrichment status"),
    (NAV_METADATA, "Metadata", "Edit ComicInfo and Comic Vine data"),
    (NAV_LISTS, "Lists", "CBL reading lists and reconciliation"),
    (NAV_ACQUIRE, "Acquire", "GetComics search, wishlist, and downloads"),
)


class PrimaryNav(QWidget):
    """Horizontal nav buttons for the four main workflows."""

    navigated = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("primaryNav")
        self._theme = "dark"
        self._buttons: dict[str, QToolButton] = {}
        self._badges: dict[str, QLabel] = {}

        layout = QHBoxLayout(self)
        layout.setContentsMargins(SPACING["lg"], SPACING["sm"], SPACING["lg"], SPACING["sm"])
        layout.setSpacing(SPACING["xs"])

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)

        for nav_id, label, tooltip in _NAV_ITEMS:
            host = QWidget()
            host_layout = QHBoxLayout(host)
            host_layout.setContentsMargins(0, 0, 0, 0)
            host_layout.setSpacing(0)

            button = QToolButton()
            button.setObjectName("navButton")
            button.setText(label)
            button.setToolTip(tooltip)
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, nid=nav_id: self._on_clicked(nid))
            self._group.addButton(button)
            self._buttons[nav_id] = button
            host_layout.addWidget(button)

            badge = QLabel("")
            badge.setObjectName("navBadge")
            badge.hide()
            self._badges[nav_id] = badge
            host_layout.addWidget(badge)

            layout.addWidget(host)

        layout.addStretch()
        self._buttons[NAV_LIBRARY].setChecked(True)
        self._set_active(NAV_LIBRARY)

    def _on_clicked(self, nav_id: str) -> None:
        self._set_active(nav_id)
        self.navigated.emit(nav_id)

    def _set_active(self, nav_id: str) -> None:
        for key, button in self._buttons.items():
            button.setProperty("active", key == nav_id)
            button.style().unpolish(button)
            button.style().polish(button)

    def set_current(self, nav_id: str) -> None:
        button = self._buttons.get(nav_id)
        if button is None:
            return
        button.setChecked(True)
        self._set_active(nav_id)

    def set_attention(self, nav_id: str, active: bool, count: int = 0) -> None:
        button = self._buttons.get(nav_id)
        badge = self._badges.get(nav_id)
        if button is None or badge is None:
            return
        button.setProperty("attention", bool(active))
        button.style().unpolish(button)
        button.style().polish(button)
        if active and count > 0:
            badge.setText(str(count))
            badge.show()
        else:
            badge.hide()

    def apply_theme(self, theme: str) -> None:
        self._theme = theme

    def resizeEvent(self, event):
        super().resizeEvent(event)
        compact = is_nav_compact(self.width())
        for nav_id, label in ((n[0], n[1]) for n in _NAV_ITEMS):
            button = self._buttons[nav_id]
            if compact:
                button.setText(label[:3])
            else:
                button.setText(label)
