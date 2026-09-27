"""Collection area: browse, series gaps, and insights."""

from PySide6.QtWidgets import QHBoxLayout, QStackedWidget, QVBoxLayout, QWidget

from comicdesk.ui.comic_list import ComicList
from comicdesk.ui.insights_panel import InsightsPanel
from comicdesk.ui.series_panel import SeriesPanel
from comicdesk.ui.shell.secondary_nav import (
    SUB_COLLECTION_BROWSE,
    SUB_COLLECTION_INSIGHTS,
    SUB_COLLECTION_SERIES,
)


class CollectionPage(QWidget):
    """Hosts browse table plus series and insights sub-views."""

    def __init__(
        self,
        comic_list: ComicList,
        series_panel: SeriesPanel,
        insights_panel: InsightsPanel,
        parent=None,
    ):
        super().__init__(parent)
        self.comic_list = comic_list
        self.series_panel = series_panel
        self.insights_panel = insights_panel
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._browse_host = QWidget()
        browse_layout = QHBoxLayout(self._browse_host)
        browse_layout.setContentsMargins(0, 0, 0, 0)
        browse_layout.setSpacing(0)
        self._browse_sidebar_layout = browse_layout
        browse_layout.addWidget(comic_list, 1)
        self.stack = QStackedWidget()
        self.stack.addWidget(self._browse_host)
        self.stack.addWidget(series_panel)
        self.stack.addWidget(insights_panel)
        layout.addWidget(self.stack, 1)
        self._sub_index = {
            SUB_COLLECTION_BROWSE: 0,
            SUB_COLLECTION_SERIES: 1,
            SUB_COLLECTION_INSIGHTS: 2,
        }

    def navigate_sub(self, sub_id: str) -> None:
        index = self._sub_index.get(sub_id, 0)
        self.stack.setCurrentIndex(index)

    def apply_theme(self, theme: str) -> None:
        self.comic_list.apply_theme(theme)
        self.series_panel.apply_theme(theme)
        self.insights_panel.apply_theme(theme)
