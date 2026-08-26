"""Main application window."""

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QMenuBar, QStatusBar, QLabel
)
from PySide6.QtCore import Qt

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

    def _setup_ui(self):
        """Set up the main UI layout."""
        self.setWindowTitle("CBL Maker")
        self.setMinimumSize(1200, 700)
        
        # Main splitter
        splitter = QSplitter(Qt.Horizontal)
        
        # Left panel - folder browser
        self.folder_panel = FolderPanel()
        self.folder_panel.folder_selected.connect(self._on_folder_selected)
        
        # Center panel - comic list
        self.comic_list = ComicList()
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
        file_menu.addAction("&Settings", self._show_settings)
        file_menu.addSeparator()
        file_menu.addAction("E&xit", self.close)
        
        # Edit menu
        edit_menu = menubar.addMenu("&Edit")
        edit_menu.addAction("&Export CBL", self.reading_list_panel.export_cbl)

    def _setup_statusbar(self):
        """Set up the status bar."""
        self.statusbar = QStatusBar()
        self.setStatusBar(self.statusbar)
        self.statusbar.showMessage("Ready")

    def _show_settings(self):
        """Show the settings dialog."""
        dialog = ConfigDialog(self.config, self)
        if dialog.exec():
            self.config = dialog.get_config()
            self.config.save()
            self.statusbar.showMessage("Settings saved")

    def _on_folder_selected(self, path):
        """Handle folder selection."""
        self.statusbar.showMessage(f"Scanning: {path}...")
        self.comic_list.load_folder(path)

    def _on_comics_selected(self, comics):
        """Handle comic selection for adding to reading list."""
        for comic in comics:
            self.reading_list_panel.add_comic(comic)
