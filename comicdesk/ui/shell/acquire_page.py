"""Unified acquisition workflow: GetComics + download queue."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QSplitter, QVBoxLayout, QWidget

from comicdesk.ui.download_queue_panel import DownloadQueuePanel
from comicdesk.ui.getcomics_panel import GetComicsPanel
from comicdesk.ui.widgets.panel_chrome import PanelChrome


class AcquirePage(QWidget):
    """Search, wishlist, and background downloads in one destination."""

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

        chrome = PanelChrome(
            "Acquire",
            "Search GetComics, manage the wishlist, and monitor the download queue.",
        )
        layout.addWidget(chrome)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self.getcomics_panel)
        splitter.addWidget(self.download_queue_panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([520, 280])
        layout.addWidget(splitter, 1)

    def apply_theme(self, theme: str) -> None:
        self.getcomics_panel.apply_theme(theme)
        self.download_queue_panel.apply_theme(theme)
