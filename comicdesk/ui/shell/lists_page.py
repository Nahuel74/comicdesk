"""Lists area: CBL editor and Comic Vine story arc import."""

from PySide6.QtWidgets import QStackedWidget, QVBoxLayout, QWidget

from comicdesk.ui.from_arc_panel import FromArcPanel
from comicdesk.ui.reading_list_panel import ReadingListPanel
from comicdesk.ui.shell.secondary_nav import SUB_LISTS_EDITOR, SUB_LISTS_FROM_ARC


class ListsPage(QWidget):
    def __init__(
        self,
        reading_list_panel: ReadingListPanel,
        from_arc_panel: FromArcPanel,
        lists_hint_banner,
        parent=None,
    ):
        super().__init__(parent)
        self.reading_list_panel = reading_list_panel
        self.from_arc_panel = from_arc_panel
        self.lists_hint_banner = lists_hint_banner
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(lists_hint_banner)
        self.stack = QStackedWidget()
        editor_host = QWidget()
        editor_layout = QVBoxLayout(editor_host)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.addWidget(reading_list_panel)
        self.stack.addWidget(editor_host)
        self.stack.addWidget(from_arc_panel)
        layout.addWidget(self.stack, 1)
        self._sub_index = {
            SUB_LISTS_EDITOR: 0,
            SUB_LISTS_FROM_ARC: 1,
        }

    def navigate_sub(self, sub_id: str) -> None:
        index = self._sub_index.get(sub_id, 0)
        self.stack.setCurrentIndex(index)
        if sub_id != SUB_LISTS_EDITOR:
            self.lists_hint_banner.hide()

    def apply_theme(self, theme: str) -> None:
        self.reading_list_panel.apply_theme(theme)
        self.from_arc_panel.apply_theme(theme)
