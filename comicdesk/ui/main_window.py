"""Main application window."""

from pathlib import Path

from PySide6.QtWidgets import QApplication, QMainWindow, QStatusBar
from PySide6.QtGui import QAction

from comicdesk.config import Config, normalize_theme
from comicdesk.ui.config_dialog import ConfigDialog
from comicdesk.ui.comic_list import ComicList
from comicdesk.ui.reading_list_panel import ReadingListPanel
from comicdesk.ui.cbz_metadata_panel import CbzMetadataPanel
from comicdesk.ui.getcomics_panel import GetComicsPanel
from comicdesk.ui.download_queue_panel import DownloadQueuePanel
from comicdesk.services.download_queue import DownloadQueueManager
from comicdesk.services.wishlist import WishlistManager
from comicdesk.ui.shell.acquire_page import AcquirePage
from comicdesk.ui.shell.app_shell import AppShell
from comicdesk.ui.shell.primary_nav import NAV_ACQUIRE, NAV_METADATA, NAV_LISTS
from comicdesk.ui.theme import (
    application_font,
    application_stylesheet,
    resolve_effective_theme,
)
from comicdesk.ui.widgets.collapsible_sidebar import CollapsibleSidebar

DEFAULT_WINDOW_WIDTH = 1200
DEFAULT_WINDOW_HEIGHT = 720


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self):
        super().__init__()
        self.config = Config.load()
        self.wishlist_manager = WishlistManager()
        self._setup_panels()
        self._setup_ui()
        self._setup_menu()
        self._setup_statusbar()
        self._connect_signals()
        self.sidebar_action.setEnabled(self.app_shell.folder_sidebar_allowed())
        self._load_initial_folder()

    def _setup_panels(self) -> None:
        self.folder_sidebar = CollapsibleSidebar(default_folder=self.config.default_folder)
        self.folder_panel = self.folder_sidebar.folder_panel
        self.comic_list = ComicList(config=self.config)
        self.reading_list_panel = ReadingListPanel(config=self.config)
        self.reading_list_panel.set_wishlist_manager(self.wishlist_manager)
        self.metadata_panel = CbzMetadataPanel(config=self.config)
        self.getcomics_panel = GetComicsPanel(config=self.config)
        self.getcomics_panel.set_wishlist_manager(self.wishlist_manager)
        self.download_queue = DownloadQueueManager(config=self.config)
        self.download_queue_panel = DownloadQueuePanel(self.download_queue, config=self.config)
        self.getcomics_panel.set_download_queue(self.download_queue)
        self.acquire_page = AcquirePage(self.getcomics_panel, self.download_queue_panel)

    def _setup_ui(self):
        self.setWindowTitle("ComicDesk[*]")
        self.setMinimumSize(880, 600)
        self.resize(DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT)

        self.app_shell = AppShell(
            folder_sidebar=self.folder_sidebar,
            comic_list=self.comic_list,
            metadata_panel=self.metadata_panel,
            reading_list_panel=self.reading_list_panel,
            acquire_page=self.acquire_page,
        )
        self.setCentralWidget(self.app_shell)
        self._apply_theme()

    def _connect_signals(self) -> None:
        self.folder_sidebar.folder_selected.connect(self._on_folder_selected)
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
        self.getcomics_panel.status_message.connect(self.statusbar.showMessage)
        self.download_queue.download_completed.connect(self._on_getcomics_download)
        self.download_queue_panel.status_message.connect(self.statusbar.showMessage)
        self.metadata_panel.metadata_saved.connect(self._on_metadata_saved)
        self.metadata_panel.comic_focus_requested.connect(self.comic_list.focus_comic)
        self.metadata_panel.dirty_changed.connect(self.setWindowModified)
        self.comic_list.comics_changed.connect(self.metadata_panel.set_comics)
        self.comic_list.files_renamed.connect(self._on_library_files_renamed)
        self.comic_list.library_root_renamed.connect(self._on_library_root_renamed)
        self.comic_list.scan_completed.connect(self._on_library_scan_completed)
        self.metadata_panel.set_comics(self.comic_list.comics)
        self.app_shell.navigation_changed.connect(self._on_navigation_changed)
        app = QApplication.instance()
        if app is not None:
            app.styleHints().colorSchemeChanged.connect(self._on_system_color_scheme_changed)

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
        if self.config.default_folder:
            default_path = Path(self.config.default_folder)
            if default_path.exists() and default_path.is_dir():
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
            self.statusbar.showMessage("Folder sidebar is only available on Library and Metadata")
            return
        self.folder_sidebar.toggle_collapsed()

    def _on_navigation_changed(self, _nav_id: str) -> None:
        self.sidebar_action.setEnabled(self.app_shell.folder_sidebar_allowed())

    def _on_comic_focused(self, comic):
        self.metadata_panel.set_comic(comic)

    def _open_metadata_tab(self, comic):
        self.metadata_panel.set_comic(comic)
        self.app_shell.navigate_to(NAV_METADATA)

    def _on_wishlist_items_added(self, count: int) -> None:
        self.app_shell.navigate_to(NAV_ACQUIRE)
        self.statusbar.showMessage(f"Added {count} item(s) to the GetComics wishlist")

    def _on_library_scan_completed(self, comics) -> None:
        removed = self.wishlist_manager.reconcile_with_library(comics)
        if removed:
            self.statusbar.showMessage(
                f"Removed {removed} acquired item(s) from the wishlist"
            )

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
        self.getcomics_panel.shutdown_workers()
        self.download_queue_panel.shutdown_workers()
        super().closeEvent(event)
