"""Main application window."""

from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QSplitter, QStatusBar, QTabWidget, QWidget, QVBoxLayout, QLabel
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction

from comicdesk.config import Config, normalize_theme
from comicdesk.ui.config_dialog import ConfigDialog
from comicdesk.ui.folder_panel import FolderPanel
from comicdesk.ui.comic_list import ComicList
from comicdesk.ui.reading_list_panel import ReadingListPanel
from comicdesk.ui.cbz_metadata_panel import CbzMetadataPanel
from comicdesk.ui.getcomics_panel import GetComicsPanel
from comicdesk.ui.download_queue_panel import DownloadQueuePanel
from comicdesk.services.download_queue import DownloadQueueManager
from comicdesk.services.wishlist import WishlistManager
from comicdesk.ui.theme import (
    SPACING,
    application_font,
    application_stylesheet,
    workspace_topbar_stylesheet,
)


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self):
        super().__init__()
        self.config = Config.load()
        self.wishlist_manager = WishlistManager()
        self._setup_ui()
        self._setup_menu()
        self._setup_statusbar()
        self.reading_list_panel.status_message.connect(self.statusbar.showMessage)
        self.reading_list_panel.dirty_changed.connect(self.setWindowModified)
        self.reading_list_panel.wishlist_items_added.connect(self._on_wishlist_items_added)
        self.metadata_panel.status_message.connect(self.statusbar.showMessage)
        self.getcomics_panel.status_message.connect(self.statusbar.showMessage)
        self.download_queue.download_completed.connect(self._on_getcomics_download)
        self.download_queue_panel.status_message.connect(self.statusbar.showMessage)
        self.metadata_panel.metadata_saved.connect(self.comic_list.refresh_comic)
        self.metadata_panel.comic_focus_requested.connect(self.comic_list.focus_comic)
        self.metadata_panel.dirty_changed.connect(self.setWindowModified)
        self.comic_list.comics_changed.connect(self.metadata_panel.set_comics)
        self.comic_list.scan_completed.connect(self._on_library_scan_completed)
        self.metadata_panel.set_comics(self.comic_list.comics)
        self._load_initial_folder()

    def _setup_ui(self):
        """Set up the main UI layout."""
        self.setWindowTitle("ComicDesk[*]")
        self.setMinimumSize(980, 600)
        workspace = QWidget()
        workspace.setObjectName("workspace")
        workspace_layout = QVBoxLayout(workspace)
        workspace_layout.setContentsMargins(0, 0, 0, 0)
        workspace_layout.setSpacing(0)

        topbar = QWidget()
        topbar.setObjectName("workspaceTopbar")
        topbar.setMinimumHeight(44)
        self._topbar = topbar
        topbar_layout = QVBoxLayout(topbar)
        topbar_layout.setContentsMargins(
            SPACING["lg"], SPACING["sm"], SPACING["lg"], SPACING["sm"]
        )
        title = QLabel("ComicDesk")
        title.setObjectName("workspaceTitle")
        topbar_layout.addWidget(title)
        hint = QLabel("Comic workspace")
        hint.setObjectName("workspaceHint")
        topbar_layout.addWidget(hint)
        workspace_layout.addWidget(topbar)

        # Responsive three-panel workspace.
        splitter = QSplitter(Qt.Horizontal)
        splitter.setObjectName("workspaceSplitter")
        splitter.setHandleWidth(6)
        splitter.setChildrenCollapsible(False)
        
        # Left panel - folder browser
        self.folder_panel = FolderPanel(default_folder=self.config.default_folder)
        self.folder_panel.folder_selected.connect(self._on_folder_selected)
        
        # Center panel - comic list
        self.comic_list = ComicList(config=self.config)
        self.comic_list.comics_selected.connect(self._on_comics_selected)
        self.comic_list.comic_focused.connect(self._on_comic_focused)
        self.comic_list.comic_edit_requested.connect(self._open_metadata_tab)
        
        # Right panel - reading list
        self.reading_list_panel = ReadingListPanel(config=self.config)
        self.reading_list_panel.set_wishlist_manager(self.wishlist_manager)
        self.comic_list.set_reading_list(self.reading_list_panel.reading_list)
        self.reading_list_panel.list_changed.connect(
            lambda: self.comic_list.set_reading_list(
                self.reading_list_panel.reading_list
            )
        )

        self.folder_panel.setMinimumWidth(180)
        self.comic_list.setMinimumWidth(360)
        self.reading_list_panel.setMinimumWidth(260)
        
        splitter.addWidget(self.folder_panel)
        splitter.addWidget(self.comic_list)
        splitter.addWidget(self.reading_list_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        splitter.setStretchFactor(2, 1)
        splitter.setSizes([230, 480, 320])
        
        self.metadata_panel = CbzMetadataPanel(config=self.config)
        self.getcomics_panel = GetComicsPanel(config=self.config)
        self.getcomics_panel.set_wishlist_manager(self.wishlist_manager)
        self.download_queue = DownloadQueueManager(config=self.config)
        self.download_queue_panel = DownloadQueuePanel(self.download_queue, config=self.config)
        self.getcomics_panel.set_download_queue(self.download_queue)
        self.tabs = QTabWidget()
        self.tabs.setObjectName("mainTabs")
        self.tabs.addTab(splitter, "Workspace")
        self.tabs.addTab(self.metadata_panel, "Metadata")
        self.tabs.addTab(self.getcomics_panel, "GetComics")
        self.tabs.addTab(self.download_queue_panel, "Downloads")
        workspace_layout.addWidget(self.tabs, 1)
        self.splitter = splitter
        self.setCentralWidget(workspace)
        self._apply_theme()

    def _apply_theme(self) -> None:
        """Apply the configured theme to the application and all panels."""
        theme = normalize_theme(self.config.theme)
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(application_stylesheet(theme))
        self.setFont(application_font())
        self.setStyleSheet("")
        self._topbar.setStyleSheet(workspace_topbar_stylesheet(theme))
        for widget in (
            self.folder_panel,
            self.comic_list,
            self.reading_list_panel,
            self.metadata_panel,
            self.getcomics_panel,
            self.download_queue_panel,
        ):
            widget.apply_theme(theme)

    def _setup_menu(self):
        """Set up the menu bar."""
        menubar = self.menuBar()

        view_menu = menubar.addMenu("&View")
        sidebar_action = QAction("Toggle &Folders Sidebar", self)
        sidebar_action.setShortcut("Ctrl+Shift+B")
        sidebar_action.triggered.connect(self.folder_panel.toggle_collapsed)
        view_menu.addAction(sidebar_action)
        
        # File menu
        file_menu = menubar.addMenu("&File")

        import_action = QAction("&Import CBL", self)
        import_action.setShortcut("Ctrl+I")
        import_action.triggered.connect(self.reading_list_panel.import_cbl)
        file_menu.addAction(import_action)

        self.import_action = import_action
        
        settings_action = QAction("&Settings", self)
        settings_action.setShortcut("Ctrl+,")
        settings_action.triggered.connect(self._show_settings)
        file_menu.addAction(settings_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("E&xit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Edit menu
        edit_menu = menubar.addMenu("&Edit")
        
        export_action = QAction("&Export CBL", self)
        export_action.setShortcut("Ctrl+E")
        export_action.triggered.connect(self.reading_list_panel.export_cbl)
        edit_menu.addAction(export_action)

    def _setup_statusbar(self):
        """Set up the status bar."""
        self.statusbar = QStatusBar()
        self.setStatusBar(self.statusbar)
        self.statusbar.showMessage("Ready")

    def _load_initial_folder(self):
        """Load initial folder if default is configured."""
        if self.config.default_folder:
            default_path = Path(self.config.default_folder)
            if default_path.exists() and default_path.is_dir():
                self._on_folder_selected(default_path)

    def _show_settings(self):
        """Show the settings dialog."""
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
            self.folder_panel.set_default_folder(self.config.default_folder)
            self._apply_theme()
            self.statusbar.showMessage("Settings saved")

    def _on_folder_selected(self, path):
        """Handle folder selection."""
        self.statusbar.showMessage(f"Scanning: {path}...")
        self.comic_list.load_folder(path)

    def _on_comics_selected(self, comics):
        """Handle comic selection for adding to reading list."""
        for comic in comics:
            self.reading_list_panel.add_comic(comic)

    def _on_comic_focused(self, comic):
        """Keep the metadata tab synchronized with the active table row."""
        self.metadata_panel.set_comic(comic)

    def _open_metadata_tab(self, comic):
        self.metadata_panel.set_comic(comic)
        self.tabs.setCurrentWidget(self.metadata_panel)

    def _on_wishlist_items_added(self, count: int) -> None:
        self.tabs.setCurrentWidget(self.getcomics_panel)
        self.statusbar.showMessage(f"Added {count} item(s) to the GetComics wishlist")

    def _on_library_scan_completed(self, comics) -> None:
        removed = self.wishlist_manager.reconcile_with_library(comics)
        if removed:
            self.statusbar.showMessage(
                f"Removed {removed} acquired item(s) from the wishlist"
            )

    def _on_getcomics_download(self, comic):
        """Refresh workspace when a download lands in the active folder."""
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
                self.folder_panel.select_folder(comic_path.parent)
                self.comic_list.load_folder(comic_path.parent)
        self._reconcile_wishlist_with_library()

    def _reconcile_wishlist_with_library(self) -> None:
        removed = self.wishlist_manager.reconcile_with_library(self.comic_list.comics)
        if removed:
            self.statusbar.showMessage(
                f"Removed {removed} acquired item(s) from the wishlist"
            )

    def closeEvent(self, event):
        """Stop background work before Qt destroys the workspace children."""
        self.comic_list.shutdown_workers()
        self.reading_list_panel.shutdown_workers()
        self.metadata_panel.shutdown_workers()
        self.getcomics_panel.shutdown_workers()
        self.download_queue_panel.shutdown_workers()
        super().closeEvent(event)
