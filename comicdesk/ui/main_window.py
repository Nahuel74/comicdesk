"""Main application window."""

import logging
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMainWindow, QProgressBar, QStatusBar, QLabel
from PySide6.QtGui import QAction

from comicdesk.startup_trace import startup_phase

from comicdesk.config import Config, normalize_theme
from comicdesk.ui.config_dialog import ConfigDialog
from comicdesk.ui.comic_list import ComicList
from comicdesk.ui.reading_list_panel import ReadingListPanel
from comicdesk.ui.cbz_metadata_panel import CbzMetadataPanel
from comicdesk.ui.pages_panel import PagesPanel
from comicdesk.ui.getcomics_panel import GetComicsPanel
from comicdesk.ui.download_queue_panel import DownloadQueuePanel
from comicdesk.ui.series_panel import SeriesPanel
from comicdesk.ui.insights_panel import InsightsPanel
from comicdesk.ui.from_arc_panel import FromArcPanel
from comicdesk.services.download_queue import DownloadQueueManager
from comicdesk.services.wishlist import WishlistManager
from comicdesk.ui.shell.acquire_page import AcquirePage
from comicdesk.ui.shell.app_shell import AppShell
from comicdesk.ui.shell.collection_page import CollectionPage
from comicdesk.ui.shell.issue_page import IssuePage
from comicdesk.ui.shell.lists_page import ListsPage
from comicdesk.ui.shell.primary_nav import NAV_ACQUIRE, NAV_ISSUE, NAV_LISTS
from comicdesk.ui.shell.secondary_nav import SUB_ACQUIRE_WISHLIST, SUB_ISSUE_METADATA
from comicdesk.ui.theme import (
    application_font,
    application_stylesheet,
    resolve_effective_theme,
)
from comicdesk.ui.widgets.collapsible_sidebar import CollapsibleSidebar

DEFAULT_WINDOW_WIDTH = 1200
DEFAULT_WINDOW_HEIGHT = 720

_startup_logger = logging.getLogger("comicdesk.startup")


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("ComicDesk[*]")
        self.setMinimumSize(880, 600)
        self.resize(DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT)
        self._setup_statusbar()
        self._startup_banner = QLabel("")
        self._startup_banner.setObjectName("startupBanner")
        self._startup_banner.setWordWrap(True)
        self._begin_startup_busy("Starting ComicDesk…")
        self.show()
        app = QApplication.instance()
        if app is not None:
            app.processEvents()

        with startup_phase("Load configuration"):
            self.config = Config.load()
        with startup_phase("Load wishlist"):
            self.wishlist_manager = WishlistManager()
        with startup_phase("Build panels"):
            self._setup_panels()
        with startup_phase("Assemble shell"):
            self._setup_ui()
        with startup_phase("Menus and signals"):
            self._setup_menu()
            self._connect_signals()
            self.sidebar_action.setEnabled(self.app_shell.folder_sidebar_allowed())
        self._end_startup_busy("Ready — opening library next")
        QTimer.singleShot(0, self._load_initial_folder)

    def _begin_startup_busy(self, message: str) -> None:
        _startup_logger.info("%s", message)
        self.statusbar.showMessage(message)
        if not hasattr(self, "_startup_progress"):
            self._startup_progress = QProgressBar()
            self._startup_progress.setFixedWidth(140)
            self._startup_progress.setFixedHeight(14)
            self._startup_progress.setTextVisible(False)
            self.statusbar.addPermanentWidget(self._startup_progress)
        self._startup_progress.setRange(0, 0)
        self._startup_progress.show()
        self._startup_banner.setText(message)

    def _end_startup_busy(self, message: str) -> None:
        _startup_logger.info("%s", message)
        self.statusbar.showMessage(message, 5000)
        if hasattr(self, "_startup_progress"):
            self._startup_progress.hide()
            self._startup_progress.setRange(0, 100)
            self._startup_progress.setValue(0)
        self._startup_banner.hide()

    def _setup_panels(self) -> None:
        _startup_logger.info("  folder sidebar")
        self.folder_sidebar = CollapsibleSidebar(default_folder=self.config.default_folder)
        self.folder_panel = self.folder_sidebar.folder_panel
        _startup_logger.info("  library list")
        self.comic_list = ComicList(config=self.config)
        self.series_panel = SeriesPanel()
        self.insights_panel = InsightsPanel()
        _startup_logger.info("  reading lists")
        self.reading_list_panel = ReadingListPanel(config=self.config)
        self.reading_list_panel.set_wishlist_manager(self.wishlist_manager)
        self.from_arc_panel = FromArcPanel(config=self.config)
        _startup_logger.info("  metadata editor")
        self.metadata_panel = CbzMetadataPanel(config=self.config)
        _startup_logger.info("  pages panel")
        self.pages_panel = PagesPanel(config=self.config)
        _startup_logger.info("  acquire panels")
        self.getcomics_panel = GetComicsPanel(config=self.config)
        self.getcomics_panel.set_wishlist_manager(self.wishlist_manager)
        self.download_queue = DownloadQueueManager(config=self.config)
        self.download_queue_panel = DownloadQueuePanel(self.download_queue, config=self.config)
        self.getcomics_panel.set_download_queue(self.download_queue)

        self.lists_hint_banner = QLabel(
            "You added comics from Collection. Reorder, sort, or export a CBL from here."
        )
        self.lists_hint_banner.setObjectName("inlineHint")
        self.lists_hint_banner.setWordWrap(True)
        self.lists_hint_banner.hide()

        self.collection_page = CollectionPage(
            self.comic_list, self.series_panel, self.insights_panel
        )
        self.issue_page = IssuePage(
            self.folder_sidebar, self.metadata_panel, self.pages_panel
        )
        self.lists_page = ListsPage(
            self.reading_list_panel, self.from_arc_panel, self.lists_hint_banner
        )
        self.acquire_page = AcquirePage(
            self.getcomics_panel, self.download_queue_panel
        )

    def _setup_ui(self):
        self.app_shell = AppShell(
            collection_page=self.collection_page,
            issue_page=self.issue_page,
            lists_page=self.lists_page,
            acquire_page=self.acquire_page,
        )
        shell_layout = self.app_shell.layout()
        if shell_layout is not None:
            shell_layout.insertWidget(0, self._startup_banner)
        self.setCentralWidget(self.app_shell)
        self._apply_theme()

    def _connect_signals(self) -> None:
        self.folder_sidebar.folder_selected.connect(self._on_folder_selected)
        self.comic_list.status_message.connect(self.statusbar.showMessage)
        self.comic_list.comics_selected.connect(self._on_comics_selected)
        self.comic_list.comic_focused.connect(self._on_comic_focused)
        self.comic_list.comic_edit_requested.connect(self._open_metadata_tab)
        self.comic_list.set_reading_list(self.reading_list_panel.reading_list)
        self.reading_list_panel.list_changed.connect(
            lambda: self.comic_list.set_reading_list(self.reading_list_panel.reading_list)
        )
        self.reading_list_panel.status_message.connect(self.statusbar.showMessage)
        self.reading_list_panel.dirty_changed.connect(self.setWindowModified)
        self.reading_list_panel.wishlist_items_added.connect(self._on_wishlist_items_added)
        self.metadata_panel.status_message.connect(self.statusbar.showMessage)
        self.pages_panel.status_message.connect(self.statusbar.showMessage)
        self.pages_panel.pages_removed.connect(self._on_pages_removed)
        self.pages_panel.pages_renamed.connect(self._on_pages_renamed)
        self.getcomics_panel.status_message.connect(self.statusbar.showMessage)
        self.download_queue.download_completed.connect(self._on_getcomics_download)
        self.download_queue_panel.status_message.connect(self.statusbar.showMessage)
        self.metadata_panel.metadata_saved.connect(self._on_metadata_saved)
        self.metadata_panel.comic_focus_requested.connect(self.comic_list.focus_comic)
        self.metadata_panel.dirty_changed.connect(self.setWindowModified)
        self.comic_list.comics_changed.connect(self._on_comics_changed)
        self.comic_list.comic_focused.connect(self.pages_panel.set_focus_comic)
        self.comic_list.table.selectionModel().selectionChanged.connect(
            self._sync_pages_library_selection
        )
        self.comic_list.files_renamed.connect(self._on_library_files_renamed)
        self.comic_list.library_root_renamed.connect(self._on_library_root_renamed)
        self.comic_list.scan_completed.connect(self._on_library_scan_completed)
        self.series_panel.wishlist_requested.connect(self._on_series_wishlist)
        self.series_panel.status_message.connect(self.statusbar.showMessage)
        self.from_arc_panel.import_requested.connect(self._on_arc_import)
        self.from_arc_panel.status_message.connect(self.statusbar.showMessage)
        self.metadata_panel.set_comics(self.comic_list.comics)
        self.pages_panel.set_comics(self.comic_list.comics)
        self.pages_panel.set_metadata_for_template(
            self.metadata_panel.metadata_snapshot_for_comic
        )
        self._sync_pages_library_selection()
        self.app_shell.navigation_changed.connect(self._on_navigation_changed)
        app = QApplication.instance()
        if app is not None:
            app.styleHints().colorSchemeChanged.connect(self._on_system_color_scheme_changed)

    def _on_comics_changed(self, comics) -> None:
        self.metadata_panel.set_comics(comics)
        self.pages_panel.set_comics(comics)
        self.series_panel.set_comics(comics)
        self.insights_panel.set_comics(comics)
        self.from_arc_panel.set_comics(comics)
    def _on_series_wishlist(self, books) -> None:
        result = self.wishlist_manager.add_books(books)
        self.app_shell.navigate_to(NAV_ACQUIRE, sub_id=SUB_ACQUIRE_WISHLIST)
        self.getcomics_panel._refresh_wishlist_table()
        if result.added:
            msg = f"Added {result.added} missing issue(s) to the wishlist"
            if result.skipped_duplicates:
                msg += f" ({result.skipped_duplicates} already on the list)"
        elif result.updated:
            msg = f"Updated {result.updated} wishlist row(s) with series metadata"
        elif result.skipped_duplicates:
            msg = "Those issues were already on the wishlist"
        else:
            msg = "No wishlist changes"
        self.statusbar.showMessage(msg)

    def _on_arc_import(self, entries) -> None:
        added = self.reading_list_panel.import_arc_entries(entries)
        self.app_shell.navigate_to(NAV_LISTS)
        self.statusbar.showMessage(f"Imported arc list with {added} entries")

    def _apply_theme(self) -> None:
        preference = normalize_theme(self.config.theme)
        app = QApplication.instance()
        resolved = resolve_effective_theme(preference, app)
        if app is not None:
            app.setStyleSheet(application_stylesheet(resolved))
        self.setFont(application_font())
        self.setStyleSheet("")
        self.app_shell.apply_theme(resolved)

    def _on_system_color_scheme_changed(self, _scheme) -> None:
        if normalize_theme(self.config.theme) == "system":
            self._apply_theme()

    def _setup_menu(self):
        menubar = self.menuBar()

        file_menu = menubar.addMenu("&File")

        import_action = QAction("&Import CBL", self)
        import_action.setShortcut("Ctrl+I")
        import_action.triggered.connect(self.reading_list_panel.import_cbl)
        file_menu.addAction(import_action)
        self.import_action = import_action

        save_action = QAction("&Save CBL", self)
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self.reading_list_panel.save_list)
        file_menu.addAction(save_action)
        self.save_action = save_action

        export_action = QAction("&Export CBL", self)
        export_action.setShortcut("Ctrl+E")
        export_action.triggered.connect(self.reading_list_panel.export_cbl)
        file_menu.addAction(export_action)
        self.export_action = export_action

        file_menu.addSeparator()

        settings_action = QAction("&Settings", self)
        settings_action.setShortcut("Ctrl+,")
        settings_action.triggered.connect(self._show_settings)
        file_menu.addAction(settings_action)

        file_menu.addSeparator()

        exit_action = QAction("E&xit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        view_menu = menubar.addMenu("&View")
        sidebar_action = QAction("Toggle &Folders Sidebar", self)
        sidebar_action.setShortcut("Ctrl+Shift+B")
        self.sidebar_action = sidebar_action
        sidebar_action.triggered.connect(self._toggle_folder_sidebar)
        view_menu.addAction(sidebar_action)

    def _setup_statusbar(self):
        self.statusbar = QStatusBar()
        self.setStatusBar(self.statusbar)
        self.statusbar.showMessage("Ready")

    def _load_initial_folder(self):
        if not self.config.default_folder:
            _startup_logger.info("No default library folder configured")
            self.statusbar.showMessage("Ready — choose a folder in the sidebar", 8000)
            return
        default_path = Path(self.config.default_folder)
        if not default_path.exists() or not default_path.is_dir():
            _startup_logger.warning("Default folder is missing or not a directory: %s", default_path)
            self.statusbar.showMessage(
                f"Default folder not found: {default_path}", 10000
            )
            return
        _startup_logger.info("Opening default library folder: %s", default_path)
        self._startup_banner.setText(f"Scanning library: {default_path}")
        self._startup_banner.show()
        self._on_folder_selected(default_path)

    def _show_settings(self):
        dialog = ConfigDialog(self.config, self)
        if dialog.exec():
            new_config = dialog.get_config()
            try:
                new_config.save()
            except OSError as error:
                self.statusbar.showMessage(f"Settings could not be saved: {error}")
                return
            self.config = new_config
            self.comic_list.config = self.config
            self.reading_list_panel.config = self.config
            self.metadata_panel.set_config(self.config)
            self.getcomics_panel.set_config(self.config)
            self.download_queue_panel.set_config(self.config)
            self.from_arc_panel.set_config(self.config)
            self.folder_sidebar.set_default_folder(self.config.default_folder)
            self._apply_theme()
            self.statusbar.showMessage("Settings saved")

    def _on_folder_selected(self, path):
        self.statusbar.showMessage(f"Loading library: {path}…")
        self.comic_list.load_folder(path)

    def _on_comics_selected(self, comics):
        added = 0
        for comic in comics:
            if self.reading_list_panel.add_comic(comic):
                added += 1
        if added:
            self.app_shell.notify_lists_attention(added)
            self.statusbar.showMessage(
                f"{added} comic(s) added — open Lists to review, sort, and export CBL"
            )

    def _toggle_folder_sidebar(self) -> None:
        if not self.app_shell.folder_sidebar_allowed():
            self.statusbar.showMessage("Folder sidebar is only available on the Issue tab")
            return
        self.folder_sidebar.toggle_collapsed()

    def _on_navigation_changed(self, _nav_id: str) -> None:
        self.sidebar_action.setEnabled(self.app_shell.folder_sidebar_allowed())

    def _on_comic_focused(self, comic):
        self.metadata_panel.set_comic(comic)

    def _open_metadata_tab(self, comic):
        self.metadata_panel.set_comic(comic)
        self.app_shell.navigate_to(NAV_ISSUE, sub_id=SUB_ISSUE_METADATA)

    def _on_wishlist_items_added(self, count: int) -> None:
        self.app_shell.navigate_to(NAV_ACQUIRE, sub_id=SUB_ACQUIRE_WISHLIST)
        self.statusbar.showMessage(f"Added {count} item(s) to the GetComics wishlist")

    def _on_library_scan_completed(self, comics) -> None:
        self._startup_banner.hide()
        self._on_comics_changed(comics)
        removed = self.wishlist_manager.reconcile_with_library(comics)
        if removed:
            self.statusbar.showMessage(
                f"Removed {removed} acquired item(s) from the wishlist"
            )

    def _on_pages_removed(self, comic, saved_path, previous_path: str = "") -> None:
        self.comic_list.refresh_comic(comic, previous_path=previous_path or "")
        page_count = getattr(comic, "page_count", "") or ""
        self.metadata_panel.notify_pages_removed(comic, page_count)

    def _on_pages_renamed(self, results) -> None:
        for comic, _saved, previous in results or []:
            self.comic_list.refresh_comic(comic, previous_path=previous or "")
        if results:
            self.statusbar.showMessage(
                f"Renamed pages inside {len(results)} archive(s)"
            )

    def _sync_pages_library_selection(self, *_args) -> None:
        self.pages_panel.set_library_selection(self.comic_list._selected_comics())

    def _on_metadata_saved(self, comic, previous_path: str = "") -> None:
        self.comic_list.refresh_comic(comic, previous_path=previous_path or "")

    def _on_library_files_renamed(self, comics) -> None:
        for comic in comics:
            self.metadata_panel.notify_comic_renamed(comic)
        self.reading_list_panel.refresh_table()
        if comics:
            self.statusbar.showMessage(
                f"Renamed {len(comics)} file(s) on disk"
            )

    def _on_library_root_renamed(self, old_root, new_root) -> None:
        new_path = Path(new_root)
        self.folder_sidebar.select_folder(new_path)
        self.statusbar.showMessage(f"Renamed library folder to {new_path.name}")

    def _on_getcomics_download(self, comic):
        comic_path = Path(comic.path)
        active_folder = getattr(self.comic_list, "current_folder", None)
        if active_folder and comic_path.parent == Path(active_folder):
            self.comic_list.refresh_comic(comic)
            self.statusbar.showMessage(f"Downloaded: {comic_path.name}")
        else:
            download_folder = (
                getattr(self.config, "getcomics_download_folder", "") or self.config.default_folder
            )
            if download_folder and comic_path.parent == Path(download_folder):
                self.folder_sidebar.select_folder(comic_path.parent)
                self.comic_list.load_folder(comic_path.parent)
        self._reconcile_wishlist_with_library()

    def _reconcile_wishlist_with_library(self) -> None:
        removed = self.wishlist_manager.reconcile_with_library(self.comic_list.comics)
        if removed:
            self.statusbar.showMessage(
                f"Removed {removed} acquired item(s) from the wishlist"
            )

    def closeEvent(self, event):
        self.comic_list.shutdown_workers()
        self.reading_list_panel.shutdown_workers()
        self.metadata_panel.shutdown_workers()
        self.pages_panel.shutdown_workers()
        self.getcomics_panel.shutdown_workers()
        self.download_queue_panel.shutdown_workers()
        super().closeEvent(event)
