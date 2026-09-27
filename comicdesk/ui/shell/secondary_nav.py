"""Secondary navigation strip under the primary workflow tabs."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QLabel, QToolButton, QVBoxLayout, QWidget

from comicdesk.ui.theme import SPACING, muted_label_stylesheet

# Collection sub-views
SUB_COLLECTION_BROWSE = "collection_browse"
SUB_COLLECTION_SERIES = "collection_series"
SUB_COLLECTION_INSIGHTS = "collection_insights"

# Issue sub-views
SUB_ISSUE_METADATA = "issue_metadata"
SUB_ISSUE_PAGES = "issue_pages"

# Lists sub-views
SUB_LISTS_EDITOR = "lists_editor"
SUB_LISTS_FROM_ARC = "lists_from_arc"

# Acquire sub-views
SUB_ACQUIRE_SEARCH = "acquire_search"
SUB_ACQUIRE_WISHLIST = "acquire_wishlist"
SUB_ACQUIRE_QUEUE = "acquire_queue"

_SECONDARY_ITEMS: dict[str, tuple[tuple[str, str, str], ...]] = {
    "collection": (
        (SUB_COLLECTION_BROWSE, "Browse", "Comic table, folder scan, and library tools"),
        (SUB_COLLECTION_SERIES, "Series", "Missing issues per series (ComicInfo Count)"),
        (SUB_COLLECTION_INSIGHTS, "Insights", "Local collection statistics"),
    ),
    "issue": (
        (SUB_ISSUE_METADATA, "Metadata", "ComicInfo fields and Comic Vine enrichment"),
        (SUB_ISSUE_PAGES, "Pages", "Archive members and page rename"),
    ),
    "lists": (
        (SUB_LISTS_EDITOR, "Editor", "CBL reading list editor"),
        (SUB_LISTS_FROM_ARC, "From arc", "Import issues from a Comic Vine story arc"),
    ),
    "acquire": (
        (SUB_ACQUIRE_SEARCH, "Search", "Search GetComics for downloads"),
        (SUB_ACQUIRE_WISHLIST, "Wishlist", "Missing issues queued for download"),
        (SUB_ACQUIRE_QUEUE, "Queue", "Sequential download queue"),
    ),
}

_AREA_LABELS = {
    "collection": "Collection",
    "issue": "Issue",
    "lists": "Lists",
    "acquire": "Acquire",
}


class SecondaryNav(QWidget):
    """Contextual sub-navigation for the active primary area."""

    navigated = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("secondaryNav")
        self._theme = "dark"
        self._area = "collection"
        self._active_sub_id = SUB_COLLECTION_BROWSE
        self._buttons: dict[str, QToolButton] = {}
        self._descriptions: dict[str, str] = {}
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        button_row = QWidget()
        self._layout = QHBoxLayout(button_row)
        self._layout.setContentsMargins(SPACING["lg"], SPACING["sm"], SPACING["lg"], SPACING["xs"])
        self._layout.setSpacing(SPACING["xs"])
        root.addWidget(button_row)

        context_row = QHBoxLayout()
        context_row.setContentsMargins(SPACING["lg"], 0, SPACING["lg"], SPACING["sm"])
        context_row.setSpacing(SPACING["sm"])
        self._area_label = QLabel()
        self._area_label.setObjectName("subNavAreaLabel")
        self._context_label = QLabel()
        self._context_label.setObjectName("subNavContext")
        self._context_label.setWordWrap(True)
        context_row.addWidget(self._area_label)
        context_row.addWidget(self._context_label, 1)
        root.addLayout(context_row)

        self._rebuild()

    def set_area(self, area: str, *, sub_id: str | None = None) -> None:
        if area not in _SECONDARY_ITEMS:
            return
        self._area = area
        self._rebuild()
        items = _SECONDARY_ITEMS[area]
        target = sub_id or items[0][0]
        if target not in self._buttons:
            target = items[0][0]
        button = self._buttons[target]
        button.setChecked(True)
        self._set_active(target)

    def current_sub_id(self) -> str:
        for sub_id, button in self._buttons.items():
            if button.isChecked():
                return sub_id
        items = _SECONDARY_ITEMS.get(self._area, ())
        return items[0][0] if items else ""

    def _rebuild(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._buttons.clear()
        self._descriptions.clear()
        for button in self._group.buttons():
            self._group.removeButton(button)
        items = _SECONDARY_ITEMS.get(self._area, ())
        for sub_id, label, tooltip in items:
            button = QToolButton()
            button.setObjectName("subNavButton")
            button.setText(label)
            button.setToolTip(tooltip)
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, sid=sub_id: self._on_clicked(sid))
            self._group.addButton(button)
            self._buttons[sub_id] = button
            self._descriptions[sub_id] = tooltip
            self._layout.addWidget(button)
        self._layout.addStretch()
        self._area_label.setText(_AREA_LABELS.get(self._area, ""))
        self._update_context(self._active_sub_id if self._active_sub_id in self._buttons else items[0][0] if items else "")

    def _on_clicked(self, sub_id: str) -> None:
        self._set_active(sub_id)
        self.navigated.emit(sub_id)

    def _set_active(self, sub_id: str) -> None:
        self._active_sub_id = sub_id
        for key, button in self._buttons.items():
            button.setProperty("active", key == sub_id)
            button.style().unpolish(button)
            button.style().polish(button)
        self._update_context(sub_id)

    def _update_context(self, sub_id: str) -> None:
        description = self._descriptions.get(sub_id, "")
        button = self._buttons.get(sub_id)
        name = button.text() if button is not None else ""
        if name and description:
            self._context_label.setText(f"{name} — {description}")
        else:
            self._context_label.setText(description)

    def apply_theme(self, theme: str) -> None:
        self._theme = theme
        muted = muted_label_stylesheet(theme, size=11)
        self._area_label.setStyleSheet(muted + " font-weight: 600;")
        self._context_label.setStyleSheet(muted)
