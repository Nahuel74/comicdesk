"""Folder browser panel."""

from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTreeView, QPushButton, QLabel
)
from PySide6.QtCore import Signal, QThread, QDir
from PySide6.QtGui import QFileSystemModel

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
    """Panel for browsing folders."""

    folder_selected = Signal(Path)

    def __init__(self):
        super().__init__()
        self._setup_ui()

    def _setup_ui(self):
        """Set up the panel UI."""
        layout = QVBoxLayout(self)
        
        label = QLabel("Folders")
        label.setStyleSheet("font-weight: bold;")
        layout.addWidget(label)
        
        # File system tree
        self.tree = QTreeView()
        self.model = QFileSystemModel()
        self.model.setRootPath(str(Path.home()))
        self.model.setFilter(QDir.Dirs | QDir.NoDotAndDotDot)
        self.tree.setModel(self.model)
        self.tree.setRootIndex(self.model.index(str(Path.home())))
        self.tree.clicked.connect(self._on_click)
        layout.addWidget(self.tree)
        
        # Scan button
        self.scan_btn = QPushButton("Scan for CBZ")
        self.scan_btn.clicked.connect(self._on_scan)
        layout.addWidget(self.scan_btn)

    def _on_click(self, index):
        """Handle tree item click."""
        path = Path(self.model.filePath(index))
        if path.is_dir():
            self.folder_selected.emit(path)

    def _on_scan(self):
        """Scan current folder for CBZ files."""
        index = self.tree.currentIndex()
        if index.isValid():
            path = Path(self.model.filePath(index))
            self.folder_selected.emit(path)
