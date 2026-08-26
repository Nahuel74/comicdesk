"""Main application window."""

from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow, QSplitter, QStatusBar, QMenu, QWidget, QVBoxLayout, QLabel
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction

from cbl_maker.config import Config
from cbl_maker.ui.config_dialog import ConfigDialog
from cbl_maker.ui.folder_panel import FolderPanel
from cbl_maker.ui.comic_list import ComicList
from cbl_maker.ui.reading_list_panel import ReadingListPanel
from cbl_maker.ui.theme import (
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
        self._setup_ui()
        self._setup_menu()
        self._setup_statusbar()
        self.reading_list_panel.status_message.connect(self.statusbar.showMessage)
        self.reading_list_panel.dirty_changed.connect(self.setWindowModified)
        self._load_initial_folder()

    def _setup_ui(self):
        """Set up the main UI layout."""
        self.setWindowTitle("CBL Maker")
        self.setMinimumSize(980, 600)
        self.setFont(application_font())
        self.setStyleSheet(application_stylesheet())

        workspace = QWidget()
        workspace.setObjectName("workspace")
        workspace_layout = QVBoxLayout(workspace)
        workspace_layout.setContentsMargins(0, 0, 0, 0)
        workspace_layout.setSpacing(0)

        topbar = QWidget()
        topbar.setObjectName("workspaceTopbar")
        topbar.setMinimumHeight(44)
        topbar.setStyleSheet(workspace_topbar_stylesheet())
        topbar_layout = QVBoxLayout(topbar)
        topbar_layout.setContentsMargins(
            SPACING["lg"], SPACING["sm"], SPACING["lg"], SPACING["sm"]
        )
        title = QLabel("CBL Maker")
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
        
        # Right panel - reading list
        self.reading_list_panel = ReadingListPanel()

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
        
        workspace_layout.addWidget(splitter, 1)
        self.splitter = splitter
        self.setCentralWidget(workspace)

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
            self.config = dialog.get_config()
            self.config.save()
            self.comic_list.config = self.config
            self.folder_panel.set_default_folder(self.config.default_folder)
            self.statusbar.showMessage("Settings saved")

    def _on_folder_selected(self, path):
        """Handle folder selection."""
        self.statusbar.showMessage(f"Scanning: {path}...")
        self.comic_list.load_folder(path)

    def _on_comics_selected(self, comics):
        """Handle comic selection for adding to reading list."""
        for comic in comics:
            self.reading_list_panel.add_comic(comic)

    def closeEvent(self, event):
        """Stop background work before Qt destroys the workspace children."""
        self.comic_list.shutdown_workers()
        super().closeEvent(event)
