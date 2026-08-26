"""Comic list panel with table view."""

from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableView,
    QPushButton, QLabel, QHeaderView, QMenu
)
from PySide6.QtCore import Signal, Qt, QThread
from PySide6.QtGui import QStandardItemModel, QStandardItem, QDesktopServices

from cbl_maker.models import Comic
from cbl_maker.services.cbz_reader import scan_folder
from cbl_maker.services.comicvine_api import ComicVineClient


class EnrichWorker(QThread):
    """Worker thread for enriching comics from Comic Vine."""
    progress = Signal(int, int)  # current, total
    finished = Signal(list)

    def __init__(self, comics, api_key):
        super().__init__()
        self.comics = comics
        self.api_key = api_key
        self._cancelled = False

    def run(self):
        client = ComicVineClient(self.api_key)
        total = len(self.comics)
        
        for i, comic in enumerate(self.comics):
            if self._cancelled:
                break
            
            if comic.web_links and not comic.has_cv_ids:
                from cbl_maker.utils.url_parser import extract_comicvine_ids
                for url in comic.web_links:
                    ids = extract_comicvine_ids(url)
                    if ids.get("issue_id"):
                        comic.cv_issue_id = ids["issue_id"]
                    if ids.get("series_id"):
                        comic.cv_series_id = ids["series_id"]
            
            self.progress.emit(i + 1, total)
        
        self.finished.emit(self.comics)

    def cancel(self):
        self._cancelled = True


class ComicListTable(QTableView):
    """Table view for comics."""

    def __init__(self):
        super().__init__()
        self._setup_model()

    def _setup_model(self):
        """Set up the table model."""
        self.model = QStandardItemModel()
        self.model.setHorizontalHeaderLabels([
            "File", "Series", "Number", "Volume", "Year", "CV URL", "Status"
        ])
        self.setModel(self.model)
        
        # Configure header
        header = self.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        for col in range(2, 7):
            header.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        
        self.setSelectionBehavior(QTableView.SelectRows)
        self.setSelectionMode(QTableView.MultiSelection)


class ComicList(QWidget):
    """Panel displaying scanned comics."""

    comics_selected = Signal(list)

    def __init__(self):
        super().__init__()
        self.comics = []
        self._setup_ui()

    def _setup_ui(self):
        """Set up the panel UI."""
        layout = QVBoxLayout(self)
        
        # Header
        header_layout = QHBoxLayout()
        label = QLabel("Comics")
        label.setStyleSheet("font-weight: bold;")
        header_layout.addWidget(label)
        
        self.enrich_btn = QPushButton("Enrich from Comic Vine")
        self.enrich_btn.clicked.connect(self._on_enrich)
        header_layout.addWidget(self.enrich_btn)
        
        layout.addLayout(header_layout)
        
        # Table
        self.table = ComicListTable()
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        layout.addWidget(self.table)
        
        # Status
        self.status_label = QLabel("No comics loaded")
        layout.addWidget(self.status_label)

    def load_folder(self, path: Path):
        """Load comics from a folder."""
        self.status_label.setText("Scanning...")
        self.worker = ScanWorker(path)
        self.worker.finished.connect(self._on_scan_complete)
        self.worker.progress.connect(lambda p: self.status_label.setText(f"Scanning: {p}"))
        self.worker.start()

    def _on_scan_complete(self, comics):
        """Handle scan completion."""
        self.comics = comics
        self._populate_table()
        self.status_label.setText(f"Found {len(comics)} comics")

    def _populate_table(self):
        """Populate the table with comics."""
        self.table.model.removeRows(0, self.table.model.rowCount())
        
        for comic in self.comics:
            row = [
                QStandardItem(comic.path.name),
                QStandardItem(comic.series_name),
                QStandardItem(comic.issue_number),
                QStandardItem(comic.volume),
                QStandardItem(comic.year),
                QStandardItem(comic.web_links[0] if comic.web_links else ""),
                QStandardItem(comic.status)
            ]
            # Make some columns read-only
            for item in row:
                item.setEditable(False)
            self.table.model.appendRow(row)

    def _on_enrich(self):
        """Enrich comics from Comic Vine."""
        # TODO: Get API key from config
        self.status_label.setText("Enriching from Comic Vine...")
        # This would need the API key from config
        pass

    def _show_context_menu(self, position):
        """Show context menu for table."""
        menu = QMenu(self)
        
        selected_rows = self.table.selectionModel().selectedRows()
        if selected_rows:
            menu.addAction("Add to Reading List", self._add_to_list)
            menu.addSeparator()
        
        menu.addAction("Open CV URL", self._open_cv_url)
        
        menu.exec(self.table.viewport().mapToGlobal(position))

    def _add_to_list(self):
        """Add selected comics to reading list."""
        selected = []
        for index in self.table.selectionModel().selectedRows():
            row = index.row()
            if row < len(self.comics):
                selected.append(self.comics[row])
        self.comics_selected.emit(selected)

    def _open_cv_url(self):
        """Open Comic Vine URL in browser."""
        index = self.table.currentIndex()
        if index.isValid():
            row = index.row()
            if row < len(self.comics):
                comic = self.comics[row]
                if comic.web_links:
                    from PySide6.QtCore import QUrl
                    QDesktopServices.openUrl(QUrl(comic.web_links[0]))
