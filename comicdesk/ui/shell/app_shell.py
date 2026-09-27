"""Main application layout: navigation, sub-views, and workflow pages."""

import logging

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLabel, QStackedWidget, QVBoxLayout, QWidget

from comicdesk.ui.shell.acquire_page import AcquirePage
from comicdesk.ui.shell.collection_page import CollectionPage
from comicdesk.ui.shell.issue_page import IssuePage
from comicdesk.ui.shell.lists_page import ListsPage
from comicdesk.ui.shell.primary_nav import (
    NAV_ACQUIRE,
    NAV_COLLECTION,
    NAV_ISSUE,
    NAV_LIBRARY,
    NAV_LISTS,
    NAV_METADATA,
    NAV_PAGES,
    PrimaryNav,
)
from comicdesk.ui.shell.secondary_nav import (
    SUB_ACQUIRE_SEARCH,
    SUB_COLLECTION_BROWSE,
    SUB_ISSUE_METADATA,
    SUB_ISSUE_PAGES,
    SUB_LISTS_EDITOR,
    SecondaryNav,
)


_logger = logging.getLogger(__name__)


class AppShell(QWidget):
    """Hosts primary navigation, secondary tabs, and stacked workflow pages."""

    navigation_changed = Signal(str)

    def __init__(
        self,
        collection_page: CollectionPage,
        issue_page: IssuePage,
        lists_page: ListsPage,
        acquire_page: AcquirePage,
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("workspace")
        self.collection_page = collection_page
        self.issue_page = issue_page
        self.lists_page = lists_page
        self.acquire_page = acquire_page
        self.comic_list = collection_page.comic_list
        self.metadata_panel = issue_page.metadata_panel
        self.pages_panel = issue_page.pages_panel
        self.reading_list_panel = lists_page.reading_list_panel
        self.getcomics_panel = acquire_page.getcomics_panel
        self.download_queue_panel = acquire_page.download_queue_panel
        self.folder_sidebar = issue_page.folder_sidebar
        self.series_panel = collection_page.series_panel
        self.from_arc_panel = lists_page.from_arc_panel
        self.lists_hint_banner = lists_page.lists_hint_banner

        self._lists_attention_count = 0
        self._show_lists_hint = False
        self._area = NAV_COLLECTION
        self._sub_id = SUB_COLLECTION_BROWSE

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.primary_nav = PrimaryNav()
        root.addWidget(self.primary_nav)
        self.secondary_nav = SecondaryNav()
        root.addWidget(self.secondary_nav)

        self.stack = QStackedWidget()
        self.stack.setObjectName("workflowStack")
        self.stack.addWidget(collection_page)
        self.stack.addWidget(issue_page)
        self.stack.addWidget(lists_page)
        self.stack.addWidget(acquire_page)
        root.addWidget(self.stack, 1)

        self._nav_index = {
            NAV_COLLECTION: 0,
            NAV_ISSUE: 1,
            NAV_LISTS: 2,
            NAV_ACQUIRE: 3,
        }
        self.primary_nav.navigated.connect(self._on_primary_nav)
        self.secondary_nav.navigated.connect(self._on_secondary_nav)
        self.secondary_nav.set_area(NAV_COLLECTION, sub_id=SUB_COLLECTION_BROWSE)
        self._attach_folder_sidebar(NAV_COLLECTION, SUB_COLLECTION_BROWSE)

    def _attach_folder_sidebar(self, area: str, sub_id: str) -> None:
        sidebar = self.folder_sidebar
        parent_layout = sidebar.parentWidget()
        if parent_layout is not None:
            layout = parent_layout.layout()
            if layout is not None:
                layout.removeWidget(sidebar)
        if area == NAV_COLLECTION and sub_id == SUB_COLLECTION_BROWSE:
            self.collection_page.navigate_sub(SUB_COLLECTION_BROWSE)
            target = self.collection_page._browse_sidebar_layout
            target.insertWidget(0, sidebar)
            sidebar.restore_visible_width()
            sidebar.setHidden(False)
            sidebar.show()
            self.collection_page._browse_host.show()
            _logger.debug("Folder sidebar attached to Collection → Browse")
        elif area == NAV_ISSUE:
            self.issue_page.navigate_sub(sub_id)
            target = self.issue_page._sidebar_layout
            target.insertWidget(0, sidebar)
            sidebar.restore_visible_width()
            sidebar.setHidden(False)
            sidebar.show()
            _logger.debug("Folder sidebar attached to Issue (%s)", sub_id)
        else:
            sidebar.hide()
            _logger.debug("Folder sidebar hidden (area=%s sub=%s)", area, sub_id)

    def _on_primary_nav(self, area: str) -> None:
        area = PrimaryNav._legacy_to_primary(area)
        self._area = area
        index = self._nav_index.get(area, 0)
        self.stack.setCurrentIndex(index)
        self.primary_nav.set_current(area)
        defaults = {
            NAV_COLLECTION: SUB_COLLECTION_BROWSE,
            NAV_ISSUE: SUB_ISSUE_METADATA,
            NAV_LISTS: SUB_LISTS_EDITOR,
            NAV_ACQUIRE: SUB_ACQUIRE_SEARCH,
        }
        sub_id = defaults.get(area, SUB_COLLECTION_BROWSE)
        self._sub_id = sub_id
        self.secondary_nav.set_area(area, sub_id=sub_id)
        self._apply_sub_nav(sub_id)
        self._attach_folder_sidebar(area, sub_id)
        if area == NAV_LISTS:
            self.primary_nav.set_attention(NAV_LISTS, False, 0)
            self._lists_attention_count = 0
            if self._show_lists_hint:
                self.lists_hint_banner.show()
                self._show_lists_hint = False
            else:
                self.lists_hint_banner.hide()
        else:
            self.lists_hint_banner.hide()
        self.navigation_changed.emit(area)

    def _on_secondary_nav(self, sub_id: str) -> None:
        self._sub_id = sub_id
        self._apply_sub_nav(sub_id)
        self._attach_folder_sidebar(self._area, sub_id)

    def _apply_sub_nav(self, sub_id: str) -> None:
        if self._area == NAV_COLLECTION:
            self.collection_page.navigate_sub(sub_id)
        elif self._area == NAV_ISSUE:
            self.issue_page.navigate_sub(sub_id)
        elif self._area == NAV_LISTS:
            self.lists_page.navigate_sub(sub_id)
        elif self._area == NAV_ACQUIRE:
            self.acquire_page.navigate_sub(sub_id)

    def folder_sidebar_allowed(self) -> bool:
        return self._area == NAV_ISSUE or (
            self._area == NAV_COLLECTION and self._sub_id == SUB_COLLECTION_BROWSE
        )

    def notify_lists_attention(self, count: int) -> None:
        if count <= 0:
            return
        self._lists_attention_count += count
        self._show_lists_hint = True
        self.primary_nav.set_attention(NAV_LISTS, True, self._lists_attention_count)

    def navigate_to(self, nav_id: str, *, sub_id: str | None = None) -> None:
        area = PrimaryNav._legacy_to_primary(nav_id)
        if sub_id is None:
            if area == NAV_ISSUE and nav_id in (NAV_PAGES, "pages"):
                sub_id = SUB_ISSUE_PAGES
            elif area == NAV_ISSUE:
                sub_id = SUB_ISSUE_METADATA
            elif area == NAV_COLLECTION and nav_id in (NAV_LIBRARY, "library"):
                sub_id = SUB_COLLECTION_BROWSE
        self._area = area
        index = self._nav_index.get(area, 0)
        self.stack.setCurrentIndex(index)
        self.primary_nav.set_current(area)
        if sub_id:
            self._sub_id = sub_id
            self.secondary_nav.set_area(area, sub_id=sub_id)
            self._apply_sub_nav(sub_id)
        else:
            self.secondary_nav.set_area(area)
            self._sub_id = self.secondary_nav.current_sub_id()
            self._apply_sub_nav(self._sub_id)
        self._attach_folder_sidebar(area, self._sub_id)
        if area == NAV_LISTS:
            self.primary_nav.set_attention(NAV_LISTS, False, 0)
            self._lists_attention_count = 0
        self.navigation_changed.emit(area)

    def current_nav_id(self) -> str:
        return self._area

    def apply_theme(self, theme: str) -> None:
        self.primary_nav.apply_theme(theme)
        self.secondary_nav.apply_theme(theme)
        self.collection_page.apply_theme(theme)
        self.issue_page.apply_theme(theme)
        self.lists_page.apply_theme(theme)
        self.acquire_page.apply_theme(theme)
