"""Folder browser panel with modern design."""

from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTreeView, QPushButton,
    QLabel, QFileSystemModel, QToolButton, QSizePolicy, QMenu
)
from PySide6.QtCore import Signal, QThread, QDir, QModelIndex, QUrl, Qt
from PySide6.QtGui import QDesktopServices

from cbl_maker.services.cbz_reader import read_cbz_metadata


class ScanWorker(QThread):
    """Worker thread for folder scanning."""
    finished = Signal(list)
    progress = Signal(str)

    def __init__(self, path: Path, recursive: bool = True):
        super().__init__()
        self.path = path
        self.recursive = recursive
        self._cancelled = False

    def run(self):
        comics = []
        pattern = "**/*.cbz" if self.recursive else "*.cbz"
        
        for cbz_file in sorted(self.path.glob(pattern)):
            if self._cancelled:
                break
            if cbz_file.is_file():
                self.progress.emit(str(cbz_file.name))
                comic = read_cbz_metadata(cbz_file)
                comics.append(comic)
        
        self.finished.emit(comics)

    def cancel(self):
        self._cancelled = True


class FolderPanel(QWidget):
    """Panel for browsing folders with navigation."""

    folder_selected = Signal(Path)

    def __init__(self, default_folder: str = ""):
        super().__init__()
        self._default_folder = default_folder
        self._current_path = None
        self._setup_ui()

    def _setup_ui(self):
        """Set up the panel UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Navigation bar
        nav_bar = QWidget()
        nav_bar.setStyleSheet("""
            QWidget {
                background-color: #2b2b2b;
                border-bottom: 1px solid #3d3d3d;
            }
        """)
        nav_layout = QHBoxLayout(nav_bar)
        nav_layout.setContentsMargins(8, 8, 8, 8)
        nav_layout.setSpacing(4)
        
        self.up_btn = QToolButton()
        self.up_btn.setText("⬆")
        self.up_btn.setToolTip("Go up")
        self.up_btn.setFixedSize(28, 28)
        self.up_btn.setStyleSheet("""
            QToolButton {
                border: none;
                font-size: 14px;
            }
            QToolButton:hover {
                background-color: #3d3d3d;
                border-radius: 4px;
            }
        """)
        self.up_btn.clicked.connect(self._go_up)
        nav_layout.addWidget(self.up_btn)
        
        self.path_label = QLabel()
        self.path_label.setStyleSheet("""
            QLabel {
                color: #e0e0e0;
                padding: 4px 8px;
                font-family: monospace;
                font-size: 12px;
            }
        """)
        self.path_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        nav_layout.addWidget(self.path_label)
        
        self.open_btn = QToolButton()
        self.open_btn.setText("📂")
        self.open_btn.setToolTip("Open in file manager")
        self.open_btn.setFixedSize(28, 28)
        self.open_btn.setStyleSheet("""
            QToolButton {
                border: none;
                font-size: 14px;
            }
            QToolButton:hover {
                background-color: #3d3d3d;
                border-radius: 4px;
            }
        """)
        self.open_btn.clicked.connect(self._open_in_manager)
        nav_layout.addWidget(self.open_btn)
        
        layout.addWidget(nav_bar)
        
        # File system tree
        self.tree = QTreeView()
        self.tree.setStyleSheet("""
            QTreeView {
                background-color: #1e1e1e;
                color: #e0e0e0;
                border: none;
                outline: none;
            }
            QTreeView::item {
                padding: 6px 4px;
                min-height: 24px;
            }
            QTreeView::item:selected {
                background-color: #264f78;
            }
            QTreeView::item:hover:!selected {
                background-color: #2d2d2d;
            }
            QTreeView::branch {
                background-color: #1e1e1e;
            }
            QTreeView::branch:hover {
                background-color: #2d2d2d;
            }
        """)
        
        self.model = QFileSystemModel()
        self.model.setRootPath(str(Path.home()))
        self.model.setFilter(QDir.Dirs | QDir.NoDotAndDotDot)
        
        self.tree.setModel(self.model)
        self.tree.setRootIndex(self.model.index(str(Path.home())))
        
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._show_context_menu)
        self.tree.doubleClicked.connect(self._on_double_click)
        self.tree.setHeaderHidden(True)
        
        # Hide all columns except name
        for col in range(1, 4):
            self.tree.hideColumn(col)
        
        layout.addWidget(self.tree)
        
        # Scan button at bottom
        btn_container = QWidget()
        btn_container.setStyleSheet("""
            QWidget {
                background-color: #2b2b2b;
                border-top: 1px solid #3d3d3d;
            }
        """)
        btn_layout = QHBoxLayout(btn_container)
        btn_layout.setContentsMargins(8, 8, 8, 8)
        
        self.scan_btn = QPushButton("Scan for CBZ")
        self.scan_btn.setStyleSheet("""
            QPushButton {
                background-color: #0e639c;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1177bb;
            }
            QPushButton:pressed {
                background-color: #094771;
            }
        """)
        self.scan_btn.clicked.connect(self._on_scan)
        btn_layout.addWidget(self.scan_btn)
        
        layout.addWidget(btn_container)
        
        # Set initial path
        self._set_initial_path()

    def _set_initial_path(self):
        """Set initial path based on priority: default > home."""
        if self._default_folder:
            default = Path(self._default_folder)
            if default.exists():
                self._navigate_to(default)
                return
        
        self._navigate_to(Path.home())

    def _navigate_to(self, path: Path):
        """Navigate to a specific folder."""
        if not path.exists() or not path.is_dir():
            return
        
        self._current_path = path
        self.path_label.setText(str(path))
        
        # Set the root index to show the folder structure
        index = self.model.index(str(path))
        if index.isValid():
            self.tree.setRootIndex(index)
            
            # Expand parent directories
            current = path
            while current != current.parent:
                parent_index = self.model.index(str(current.parent))
                if parent_index.isValid():
                    self.tree.expand(parent_index)
                current = current.parent

    def _go_up(self):
        """Navigate to parent folder."""
        if self._current_path and self._current_path != self._current_path.parent:
            self._navigate_to(self._current_path.parent)

    def _open_in_manager(self):
        """Open current folder in system file manager."""
        if self._current_path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._current_path)))

    def _on_double_click(self, index: QModelIndex):
        """Handle double click - navigate into folder (no scan)."""
        path = Path(self.model.filePath(index))
        if path.is_dir():
            self._navigate_to(path)

    def _show_context_menu(self, position):
        """Show context menu for tree items."""
        index = self.tree.indexAt(position)
        if not index.isValid():
            return
        
        path = Path(self.model.filePath(index))
        if not path.is_dir():
            return
        
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #2b2b2b;
                color: #e0e0e0;
                border: 1px solid #3d3d3d;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 24px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #264f78;
            }
        """)
        
        scan_action = menu.addAction("📂 Scan for CBZ")
        scan_action.triggered.connect(lambda: self._scan_folder(path))
        
        open_action = menu.addAction("📁 Open in File Manager")
        open_action.triggered.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))))
        
        menu.exec(self.tree.viewport().mapToGlobal(position))

    def _scan_folder(self, path: Path):
        """Scan a specific folder."""
        self._current_path = path
        self.path_label.setText(str(path))
        self.folder_selected.emit(path)

    def _on_scan(self):
        """Scan current folder for CBZ files."""
        if self._current_path:
            self.folder_selected.emit(self._current_path)

    def set_default_folder(self, folder: str):
        """Update the default folder."""
        self._default_folder = folder
        if not self._current_path:
            self._set_initial_path()
