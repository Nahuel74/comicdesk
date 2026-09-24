"""Main application layout: sidebar, navigation, and workflow pages."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QStackedWidget, QLabel, QVBoxLayout, QWidget

from comicdesk.ui.comic_list import ComicList
from comicdesk.ui.cbz_metadata_panel import CbzMetadataPanel
from comicdesk.ui.pages_panel import PagesPanel
from comicdesk.ui.reading_list_panel import ReadingListPanel
from comicdesk.ui.shell.acquire_page import AcquirePage
from comicdesk.ui.shell.primary_nav import (
    NAV_ACQUIRE,
    NAV_LIBRARY,
    NAV_LISTS,
    NAV_METADATA,
    NAV_PAGES,
    PrimaryNav,
)
from comicdesk.ui.widgets.collapsible_sidebar import CollapsibleSidebar
from comicdesk.ui.widgets.panel_chrome import PanelChrome


class AppShell(QWidget):
    """Hosts primary navigation and stacked workflow pages."""

    navigation_changed = Signal(str)

    def __init__(
        self,
        folder_sidebar: CollapsibleSidebar,
        comic_list: ComicList,
        metadata_panel: CbzMetadataPanel,
        pages_panel: PagesPanel,
        reading_list_panel: ReadingListPanel,
        acquire_page: AcquirePage,
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("workspace")
        self.folder_sidebar = folder_sidebar
        self.comic_list = comic_list
        self.metadata_panel = metadata_panel
        self.pages_panel = pages_panel
        self.reading_list_panel = reading_list_panel
        self.acquire_page = acquire_page
        self.getcomics_panel = acquire_page.getcomics_panel
        self.download_queue_panel = acquire_page.download_queue_panel
        self._lists_attention_count = 0
        self._show_lists_hint = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.primary_nav = PrimaryNav()
        root.addWidget(self.primary_nav)

        self.stack = QStackedWidget()
        self.stack.setObjectName("workflowStack")

        self._library_sidebar_host = QWidget()
        self._library_sidebar_layout = QHBoxLayout(self._library_sidebar_host)
        self._library_sidebar_layout.setContentsMargins(0, 0, 0, 0)
        self._library_sidebar_layout.setSpacing(0)

        self._metadata_sidebar_host = QWidget()
        self._metadata_sidebar_layout = QHBoxLayout(self._metadata_sidebar_host)
        self._metadata_sidebar_layout.setContentsMargins(0, 0, 0, 0)
        self._metadata_sidebar_layout.setSpacing(0)

        self._pages_sidebar_host = QWidget()
        self._pages_sidebar_layout = QHBoxLayout(self._pages_sidebar_host)
        self._pages_sidebar_layout.setContentsMargins(0, 0, 0, 0)
        self._pages_sidebar_layout.setSpacing(0)

        self.lists_hint_banner = QLabel(
            "You added comics from Library. Reorder, sort, or export a CBL from here."
        )
        self.lists_hint_banner.setObjectName("inlineHint")
        self.lists_hint_banner.setWordWrap(True)
        self.lists_hint_banner.hide()

        self.stack.addWidget(self._build_library_page())
        self.stack.addWidget(self._wrap_metadata_page())
        self.stack.addWidget(self._wrap_pages_page())
        self.stack.addWidget(self._wrap_lists_page())
        self.stack.addWidget(self.acquire_page)

        root.addWidget(self.stack, 1)

        self._nav_index = {
            NAV_LIBRARY: 0,
            NAV_METADATA: 1,
            NAV_PAGES: 2,
            NAV_LISTS: 3,
            NAV_ACQUIRE: 4,
        }
        self.primary_nav.navigated.connect(self.navigate_to)
        self._attach_sidebar_to(NAV_LIBRARY)

    def _build_library_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        chrome = PanelChrome(
            "Library",
            "Select a folder, scan comic archives, and review Comic Vine enrichment status.",
        )
        layout.addWidget(chrome)

        self._library_sidebar_layout.addWidget(self.comic_list, 1)
        layout.addWidget(self._library_sidebar_host, 1)
        return page

    def _wrap_metadata_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        chrome = PanelChrome(
            "Metadata",
            "Draft changes, search Comic Vine, and commit ComicInfo.xml updates.",
        )
        layout.addWidget(chrome)

        self._metadata_sidebar_layout.addWidget(self.metadata_panel, 1)
        layout.addWidget(self._metadata_sidebar_host, 1)
        return page

    def _wrap_pages_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        chrome = PanelChrome(
            "Pages",
            "Review archive image pages and remove credits, watermarks, and other extras.",
        )
        layout.addWidget(chrome)

        self._pages_sidebar_layout.addWidget(self.pages_panel, 1)
        layout.addWidget(self._pages_sidebar_host, 1)
        return page

    def _wrap_lists_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        chrome = PanelChrome(
            "Reading lists",
            "Import CBL files, reconcile with your library, sort, and preview XML.",
        )
        layout.addWidget(chrome)
        layout.addWidget(self.lists_hint_banner)
        layout.addWidget(self.reading_list_panel, 1)
        return page

    def _attach_sidebar_to(self, nav_id: str) -> None:
        parent_layout = self.folder_sidebar.parentWidget()
        if parent_layout is not None:
            layout = parent_layout.layout()
            if layout is not None:
                layout.removeWidget(self.folder_sidebar)
        if nav_id not in (NAV_LIBRARY, NAV_METADATA, NAV_PAGES):
            self.folder_sidebar.hide()
            return
        if nav_id == NAV_LIBRARY:
            target = self._library_sidebar_layout
        elif nav_id == NAV_METADATA:
            target = self._metadata_sidebar_layout
        else:
            target = self._pages_sidebar_layout
        target.insertWidget(0, self.folder_sidebar)
        self.folder_sidebar.restore_visible_width()
        self.folder_sidebar.show()

    def folder_sidebar_allowed(self) -> bool:
        return self.current_nav_id() in (NAV_LIBRARY, NAV_METADATA, NAV_PAGES)

    def notify_lists_attention(self, count: int) -> None:
        if count <= 0:
            return
        self._lists_attention_count += count
        self._show_lists_hint = True
        self.primary_nav.set_attention(NAV_LISTS, True, self._lists_attention_count)

    def navigate_to(self, nav_id: str) -> None:
        index = self._nav_index.get(nav_id)
        if index is None:
            return
        self.stack.setCurrentIndex(index)
        self.primary_nav.set_current(nav_id)
        self._attach_sidebar_to(nav_id)
        if nav_id == NAV_LISTS:
            self.primary_nav.set_attention(NAV_LISTS, False, 0)
            self._lists_attention_count = 0
            if self._show_lists_hint:
                self.lists_hint_banner.show()
                self._show_lists_hint = False
            else:
                self.lists_hint_banner.hide()
        else:
            self.lists_hint_banner.hide()
        self.navigation_changed.emit(nav_id)

    def current_nav_id(self) -> str:
        for nav_id, index in self._nav_index.items():
            if self.stack.currentIndex() == index:
                return nav_id
        return NAV_LIBRARY

    def apply_theme(self, theme: str) -> None:
        self.primary_nav.apply_theme(theme)
        self.folder_sidebar.apply_theme(theme)
        self.comic_list.apply_theme(theme)
        self.metadata_panel.apply_theme(theme)
        self.pages_panel.apply_theme(theme)
        self.reading_list_panel.apply_theme(theme)
        self.acquire_page.apply_theme(theme)
