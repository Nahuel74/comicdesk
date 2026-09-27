"""Issue area: metadata editor and pages tools for one file."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QStackedWidget, QVBoxLayout, QWidget

from comicdesk.ui.cbz_metadata_panel import CbzMetadataPanel
from comicdesk.ui.pages_panel import PagesPanel
from comicdesk.ui.shell.secondary_nav import SUB_ISSUE_METADATA, SUB_ISSUE_PAGES
from comicdesk.ui.widgets.collapsible_sidebar import CollapsibleSidebar


class IssuePage(QWidget):
    """Folder sidebar with metadata or pages on the right."""

    def __init__(
        self,
        folder_sidebar: CollapsibleSidebar,
        metadata_panel: CbzMetadataPanel,
        pages_panel: PagesPanel,
        parent=None,
    ):
        super().__init__(parent)
        self.folder_sidebar = folder_sidebar
        self.metadata_panel = metadata_panel
        self.pages_panel = pages_panel
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._sidebar_host = QWidget()
        self._sidebar_layout = QHBoxLayout(self._sidebar_host)
        self._sidebar_layout.setContentsMargins(0, 0, 0, 0)
        self._sidebar_layout.setSpacing(0)
        self._sidebar_layout.addWidget(folder_sidebar)
        self.stack = QStackedWidget()
        self.stack.addWidget(metadata_panel)
        self.stack.addWidget(pages_panel)
        self._sidebar_layout.addWidget(self.stack, 1)
        layout.addWidget(self._sidebar_host, 1)
        self._sub_index = {
            SUB_ISSUE_METADATA: 0,
            SUB_ISSUE_PAGES: 1,
        }

    def navigate_sub(self, sub_id: str) -> None:
        index = self._sub_index.get(sub_id, 0)
        self.stack.setCurrentIndex(index)

    def apply_theme(self, theme: str) -> None:
        self.folder_sidebar.apply_theme(theme)
        self.metadata_panel.apply_theme(theme)
        self.pages_panel.apply_theme(theme)
