"""Acquisition workflow with search, wishlist, and queue sub-views."""

from PySide6.QtWidgets import QStackedWidget, QVBoxLayout, QWidget

from comicdesk.ui.download_queue_panel import DownloadQueuePanel
from comicdesk.ui.getcomics_panel import GetComicsPanel
from comicdesk.ui.shell.secondary_nav import (
    SUB_ACQUIRE_QUEUE,
    SUB_ACQUIRE_SEARCH,
    SUB_ACQUIRE_WISHLIST,
)


class AcquirePage(QWidget):
    def __init__(
        self,
        getcomics_panel: GetComicsPanel,
        download_queue_panel: DownloadQueuePanel,
        parent=None,
    ):
        super().__init__(parent)
        self.getcomics_panel = getcomics_panel
        self.download_queue_panel = download_queue_panel
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.stack = QStackedWidget()
        self.stack.addWidget(getcomics_panel)
        self.stack.addWidget(download_queue_panel)
        layout.addWidget(self.stack, 1)
        self._sub_index = {
            SUB_ACQUIRE_SEARCH: 0,
            SUB_ACQUIRE_WISHLIST: 0,
            SUB_ACQUIRE_QUEUE: 1,
        }
        self.navigate_sub(SUB_ACQUIRE_SEARCH)

    def navigate_sub(self, sub_id: str) -> None:
        index = self._sub_index.get(sub_id, 0)
        self.stack.setCurrentIndex(index)
        if sub_id == SUB_ACQUIRE_SEARCH:
            self.getcomics_panel.set_acquire_view_mode("search")
        elif sub_id == SUB_ACQUIRE_WISHLIST:
            self.getcomics_panel.set_acquire_view_mode("wishlist")
        elif sub_id == SUB_ACQUIRE_QUEUE:
            self.getcomics_panel.set_acquire_view_mode("hidden")
        else:
            self.getcomics_panel.set_acquire_view_mode("search")

    def apply_theme(self, theme: str) -> None:
        self.getcomics_panel.apply_theme(theme)
        self.download_queue_panel.apply_theme(theme)
