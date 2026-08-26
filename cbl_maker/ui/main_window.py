"""Main application window."""

from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow, QSplitter, QStatusBar, QMenuBar, QMenu
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction

from cbl_maker.config import Config
from cbl_maker.ui.config_dialog import ConfigDialog
from cbl_maker.ui.folder_panel import FolderPanel
from cbl_maker.ui.comic_list import ComicList
from cbl_maker.ui.reading_list_panel import ReadingListPanel


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self):
        super().__init__()
        self.config = Config.load()
        self._setup_ui()
        self._setup_menu()
        self._setup_statusbar()
        self._load_initial_folder()

    def _setup_ui(self):
        """Set up the main UI layout."""
        self.setWindowTitle("CBL Maker")
        self.setMinimumSize(1200, 700)
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1e1e1e;
            }
            QSplitter::handle {
                background-color: #3d3d3d;
                width: 2px;
            }
            QMenuBar {
                background-color: #2b2b2b;
                color: #e0e0e0;
                border-bottom: 1px solid #3d3d3d;
            }
            QMenuBar::item:selected {
                background-color: #3d3d3d;
            }
            QMenu {
                background-color: #2b2b2b;
                color: #e0e0e0;
                border: 1px solid #3d3d3d;
            }
            QMenu::item:selected {
                background-color: #264f78;
            }
            QStatusBar {
                background-color: #2b2b2b;
                color: #e0e0e0;
                border-top: 1px solid #3d3d3d;
            }
        """)
        
        # Main splitter
        splitter = QSplitter(Qt.Horizontal)
        splitter.setStyleSheet("QSplitter { background-color: #1e1e1e; }")
        
        # Left panel - folder browser
        self.folder_panel = FolderPanel(default_folder=self.config.default_folder)
        self.folder_panel.folder_selected.connect(self._on_folder_selected)
        
        # Center panel - comic list
        self.comic_list = ComicList(config=self.config)
        self.comic_list.comics_selected.connect(self._on_comics_selected)
        
        # Right panel - reading list
        self.reading_list_panel = ReadingListPanel()
        
        splitter.addWidget(self.folder_panel)
        splitter.addWidget(self.comic_list)
        splitter.addWidget(self.reading_list_panel)
        splitter.setSizes([250, 500, 350])
        
        self.setCentralWidget(splitter)

    def _setup_menu(self):
        """Set up the menu bar."""
        menubar = self.menuBar()
        
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
