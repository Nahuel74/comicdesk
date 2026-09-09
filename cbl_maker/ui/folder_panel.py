"""Compact, collapsible folder browser sidebar."""

from pathlib import Path

from PySide6.QtCore import (
    QDir, QModelIndex, QSortFilterProxyModel, QThread, QTimer, Qt, QUrl,
    Signal,
)
from PySide6.QtGui import QDesktopServices, QFontMetrics
from PySide6.QtWidgets import (
    QFileSystemModel, QHBoxLayout, QLabel, QMenu, QPushButton, QSizePolicy,
    QToolButton, QTreeView, QVBoxLayout, QWidget,
)

from cbl_maker.services.cbz_reader import read_cbz_metadata


class _FolderSortProxy(QSortFilterProxyModel):
    """Proxy that always sorts directories alphabetically A-Z, case-insensitive."""

    def lessThan(self, source_left, source_right):
        data_left = self.sourceModel().data(source_left, Qt.DisplayRole)
        data_right = self.sourceModel().data(source_right, Qt.DisplayRole)
        return str(data_left).lower() < str(data_right).lower()


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
                comics.append(read_cbz_metadata(cbz_file))
        self.finished.emit(comics)

    def cancel(self):
        self._cancelled = True


class FolderPanel(QWidget):
    """Folder navigation with a compact header and a collapsible body."""

    folder_selected = Signal(Path)
    collapsed_changed = Signal(bool)

    _dark_button_style = """
        QToolButton { border: none; font-size: 14px; }
        QToolButton:hover { background-color: #3d3d3d; border-radius: 4px; }
    """

    def __init__(self, default_folder: str = ""):
        super().__init__()
        self._default_folder = default_folder
        self._current_path = None
        self._collapsed = False
        self._expanded_width = 230
        self._setup_ui()

    def _button(self, text: str, tooltip: str) -> QToolButton:
        button = QToolButton()
        button.setText(text)
        button.setToolTip(tooltip)
        button.setFixedSize(28, 28)
        button.setStyleSheet(self._dark_button_style)
        return button

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.header = QWidget()
        self.header.setStyleSheet("background-color:#252526; border-bottom:1px solid #3d3d3d;")
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(10, 6, 6, 6)
        self.title_label = QLabel("FOLDERS")
        self.title_label.setStyleSheet("color:#b8b8b8; font-size:11px; font-weight:bold;")
        header_layout.addWidget(self.title_label)
        header_layout.addStretch()
        self.collapse_btn = self._button("‹", "Collapse folders sidebar")
        self.collapse_btn.clicked.connect(self.toggle_collapsed)
        header_layout.addWidget(self.collapse_btn)
        layout.addWidget(self.header)

        self.navigation = QWidget()
        self.navigation.setStyleSheet("background-color:#2b2b2b; border-bottom:1px solid #3d3d3d;")
        nav_layout = QHBoxLayout(self.navigation)
        nav_layout.setContentsMargins(8, 6, 8, 6)
        nav_layout.setSpacing(4)
        self.up_btn = self._button("⬆", "Go up")
        self.up_btn.clicked.connect(self._go_up)
        nav_layout.addWidget(self.up_btn)
        self.path_label = QLabel()
        self.path_label.setStyleSheet("color:#e0e0e0; padding:4px 8px; font-family:monospace; font-size:12px;")
        self.path_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        nav_layout.addWidget(self.path_label)
        self.open_btn = self._button("📂", "Open in file manager")
        self.open_btn.clicked.connect(self._open_in_manager)
        nav_layout.addWidget(self.open_btn)
        layout.addWidget(self.navigation)

        self.tree = QTreeView()
        self.tree.setStyleSheet("""
            QTreeView { background-color:#1e1e1e; color:#e0e0e0; border:none; outline:none; }
            QTreeView::item { padding:6px 4px; min-height:24px; }
            QTreeView::item:selected { background-color:#264f78; }
            QTreeView::item:hover:!selected { background-color:#2d2d2d; }
            QTreeView::branch { background-color:#1e1e1e; }
            QTreeView::branch:hover { background-color:#2d2d2d; }
        """)
        self.model = QFileSystemModel()
        self.model.setRootPath(str(Path.home()))
        self.model.setFilter(QDir.Dirs | QDir.NoDotAndDotDot)
        self.proxy = _FolderSortProxy()
        self.proxy.setSourceModel(self.model)
        self.proxy.sort(0, Qt.AscendingOrder)
        self.tree.setModel(self.proxy)
        self.tree.setRootIndex(
            self.proxy.mapFromSource(self.model.index(str(Path.home())))
        )
        self.tree.setSortingEnabled(True)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._show_context_menu)
        self.tree.doubleClicked.connect(self._on_double_click)
        self.tree.setHeaderHidden(True)
        for column in range(1, 4):
            self.tree.hideColumn(column)
        layout.addWidget(self.tree)
        self.model.directoryLoaded.connect(self._deferred_sort)

        self.footer = QWidget()
        self.footer.setStyleSheet("background-color:#2b2b2b; border-top:1px solid #3d3d3d;")
        footer_layout = QHBoxLayout(self.footer)
        footer_layout.setContentsMargins(8, 8, 8, 8)
        self.scan_btn = QPushButton("Scan for CBZ")
        self.scan_btn.setToolTip("Scan current folder for CBZ files")
        self.scan_btn.setStyleSheet("""
            QPushButton { background-color:#0e639c; color:white; border:none; padding:8px 16px;
                border-radius:4px; font-weight:bold; }
            QPushButton:hover { background-color:#1177bb; }
            QPushButton:pressed { background-color:#094771; }
        """)
        self.scan_btn.clicked.connect(self._on_scan)
        footer_layout.addWidget(self.scan_btn)
        layout.addWidget(self.footer)
        self._set_initial_path()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._current_path and not self._collapsed:
            width = max(20, self.path_label.width() - 16)
            self.path_label.setText(QFontMetrics(self.path_label.font()).elidedText(
                str(self._current_path), Qt.ElideMiddle, width))

    def toggle_collapsed(self):
        """Collapse to an action rail or restore the full folder browser."""
        self._collapsed = not self._collapsed
        if self._collapsed:
            self._expanded_width = max(self.width(), self._expanded_width)
            self.setMinimumWidth(48)
            self.setMaximumWidth(48)
            self.navigation.hide()
            self.tree.hide()
            self.title_label.hide()
            self.scan_btn.setFixedWidth(28)
            self.scan_btn.setText("✓")
            self.scan_btn.setToolTip("Scan current folder for CBZ files")
            self.collapse_btn.setText("›")
            self.collapse_btn.setToolTip("Expand folders sidebar")
        else:
            self.setMaximumWidth(16777215)
            self.setMinimumWidth(180)
            self.navigation.show()
            self.tree.show()
            self.title_label.show()
            self.scan_btn.setMinimumWidth(0)
            self.scan_btn.setMaximumWidth(16777215)
            self.scan_btn.setText("Scan for CBZ")
            self.collapse_btn.setText("‹")
            self.collapse_btn.setToolTip("Collapse folders sidebar")
            self.resize(self._expanded_width, self.height())
            self._update_path_label()
        self.collapsed_changed.emit(self._collapsed)

    def _update_path_label(self):
        if self._current_path:
            self.path_label.setToolTip(str(self._current_path))
            self.path_label.setText(QFontMetrics(self.path_label.font()).elidedText(
                str(self._current_path), Qt.ElideMiddle, max(20, self.path_label.width() - 16)))

    def _set_initial_path(self):
        if self._default_folder:
            default = Path(self._default_folder)
            if default.exists():
                self._navigate_to(default)
                return
        self._navigate_to(Path.home())

    def _navigate_to(self, path: Path):
        if not path.exists() or not path.is_dir():
            return
        self._current_path = path
        self._update_path_label()
        source_index = self.model.index(str(path))
        if source_index.isValid():
            proxy_index = self.proxy.mapFromSource(source_index)
            if proxy_index.isValid():
                self.tree.setRootIndex(proxy_index)

    def _go_up(self):
        if self._current_path and self._current_path != self._current_path.parent:
            self._navigate_to(self._current_path.parent)

    def _open_in_manager(self):
        if self._current_path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._current_path)))

    def _on_double_click(self, index: QModelIndex):
        source_index = self.proxy.mapToSource(index)
        path = Path(self.model.filePath(source_index))
        if path.is_dir():
            self._navigate_to(path)

    def _deferred_sort(self, _path: str):
        QTimer.singleShot(0, lambda: self.proxy.sort(0, Qt.AscendingOrder))

    def _show_context_menu(self, position):
        proxy_index = self.tree.indexAt(position)
        if not proxy_index.isValid():
            return
        source_index = self.proxy.mapToSource(proxy_index)
        path = Path(self.model.filePath(source_index))
        if not path.is_dir():
            return
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { background:#2b2b2b; color:#e0e0e0; border:1px solid #3d3d3d; padding:4px; } QMenu::item { padding:6px 24px; } QMenu::item:selected { background:#264f78; }")
        menu.addAction("📂 Scan for CBZ", lambda: self._scan_folder(path))
        menu.addAction("📁 Open in File Manager", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))))
        menu.exec(self.tree.viewport().mapToGlobal(position))

    def _scan_folder(self, path: Path):
        self._current_path = path
        self._update_path_label()
        self.folder_selected.emit(path)

    def _on_scan(self):
        if self._current_path:
            self.folder_selected.emit(self._current_path)

    def set_default_folder(self, folder: str):
        self._default_folder = folder
        if not self._current_path:
            self._set_initial_path()

    def select_folder(self, path: Path):
        """Navigate to a folder and emit folder_selected."""
        self._scan_folder(path)
