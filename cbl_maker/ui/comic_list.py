"""Comic list panel with table view."""

from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableView,
    QPushButton, QLabel, QHeaderView, QMenu, QSizePolicy
)
from PySide6.QtCore import Signal, Qt, QThread
from PySide6.QtGui import QStandardItemModel, QStandardItem, QDesktopServices, QAction

from cbl_maker.models import Comic
from cbl_maker.services.cbz_reader import read_cbz_metadata
from cbl_maker.services.comicvine_api import (
    ComicVineClient, ComicVineError, RateLimitError, InvalidAPIKeyError
)
from cbl_maker.utils.url_parser import extract_comicvine_ids


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


class EnrichWorker(QThread):
    """Worker thread for enriching comics from Comic Vine."""
    progress = Signal(int, int)
    finished = Signal(list, bool)
    error = Signal(str)

    def __init__(self, comics: list[Comic], api_key: str):
        super().__init__()
        self.comics = comics
        self.api_key = api_key
        self._cancelled = False

    def run(self):
        client = ComicVineClient(self.api_key)
        total = len(self.comics)
        error_occurred = False

        for i, comic in enumerate(self.comics):
            if self._cancelled:
                break

            try:
                self._enrich_comic(comic, client)
            except InvalidAPIKeyError:
                self.error.emit("Invalid API key")
                error_occurred = True
                break
            except RateLimitError:
                self.error.emit("Rate limit exceeded — try again later")
                error_occurred = True
                break
            except ComicVineError as e:
                self.error.emit(f"API error: {e}")
                error_occurred = True

            self.progress.emit(i + 1, total)

        self.finished.emit(self.comics, error_occurred)

    def _enrich_comic(self, comic: Comic, client) -> None:
        """Enrich a single comic using the Comic Vine API."""
        # Case 1: Already has both IDs — skip
        if comic.has_cv_ids:
            return

        # Case 2: Has issue_id — fetch issue to get series_id
        if comic.cv_issue_id:
            issue = client.get_issue(comic.cv_issue_id)
            if issue.series_id and not comic.cv_series_id:
                comic.cv_series_id = issue.series_id
            self._apply_issue_data(comic, issue)
            return

        # Case 3: Has web_links — parse for issue_id then fetch
        if comic.web_links:
            for url in comic.web_links:
                ids = extract_comicvine_ids(url)
                if ids.get("issue_id"):
                    comic.cv_issue_id = ids["issue_id"]
                    self._fetch_and_apply_issue(comic, client, ids["issue_id"])
                    return
                if ids.get("series_id") and not comic.cv_series_id:
                    comic.cv_series_id = ids["series_id"]

        # Case 4: Has series_id but no issue_id — already parsed from URL
        if comic.cv_series_id:
            return

        # Case 5: No IDs at all — search by title + issue number
        if comic.series_name and comic.issue_number:
            query = f"{comic.series_name} #{comic.issue_number}"
            results = client.search_issue(query)
            if results:
                best = results[0]
                comic.cv_issue_id = best.id
                if best.series_id:
                    comic.cv_series_id = best.series_id
                self._apply_issue_data(comic, best)

    def _fetch_and_apply_issue(self, comic: Comic, client, issue_id: str) -> None:
        """Fetch issue from API and apply data to comic."""
        issue = client.get_issue(issue_id)
        if issue.series_id and not comic.cv_series_id:
            comic.cv_series_id = issue.series_id
        self._apply_issue_data(comic, issue)

    def _apply_issue_data(self, comic: Comic, issue) -> None:
        """Apply issue data from API response to comic, filling missing fields."""
        if not comic.series_name and issue.series_name:
            comic.series_name = issue.series_name
        if not comic.volume and issue.volume:
            comic.volume = issue.volume
        if not comic.issue_number and issue.issue_number:
            comic.issue_number = issue.issue_number
        if not comic.year and issue.cover_date:
            comic.year = issue.cover_date[:4]

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
            "File", "Series", "Number", "Volume", "Year", "Status"
        ])
        self.setModel(self.model)
        
        header = self.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        for col in range(2, 6):
            header.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        
        self.setSelectionBehavior(QTableView.SelectRows)
        self.setSelectionMode(QTableView.MultiSelection)


class ComicList(QWidget):
    """Panel displaying scanned comics."""

    comics_selected = Signal(list)

    def __init__(self, config=None):
        super().__init__()
        self.comics = []
        self.config = config
        self._setup_ui()

    def _setup_ui(self):
        """Set up the panel UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Header
        header = QWidget()
        header.setStyleSheet("""
            QWidget {
                background-color: #2b2b2b;
                border-bottom: 1px solid #3d3d3d;
                padding: 8px;
            }
        """)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 12, 12, 12)
        
        label = QLabel("Comics")
        label.setStyleSheet("""
            QLabel {
                color: #e0e0e0;
                font-size: 14px;
                font-weight: bold;
            }
        """)
        header_layout.addWidget(label)
        
        header_layout.addStretch()
        
        self.enrich_btn = QPushButton("Enrich from Comic Vine")
        self.enrich_btn.setStyleSheet("""
            QPushButton {
                background-color: #0e639c;
                color: white;
                border: none;
                padding: 6px 12px;
                border-radius: 4px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #1177bb;
            }
            QPushButton:pressed {
                background-color: #094771;
            }
            QPushButton:disabled {
                background-color: #3d3d3d;
                color: #6d6d6d;
            }
        """)
        self.enrich_btn.clicked.connect(self._on_enrich)
        header_layout.addWidget(self.enrich_btn)
        
        layout.addWidget(header)
        
        # Table
        self.table = ComicListTable()
        self.table.setStyleSheet("""
            QTableView {
                background-color: #1e1e1e;
                color: #e0e0e0;
                border: none;
                gridline-color: #2d2d2d;
            }
            QTableView::item {
                padding: 6px;
            }
            QTableView::item:selected {
                background-color: #264f78;
            }
            QTableView::item:hover:!selected {
                background-color: #2d2d2d;
            }
            QHeaderView::section {
                background-color: #2b2b2b;
                color: #e0e0e0;
                padding: 8px;
                border: none;
                border-right: 1px solid #3d3d3d;
                border-bottom: 1px solid #3d3d3d;
                font-weight: bold;
            }
        """)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        layout.addWidget(self.table)
        
        # Status bar
        status_bar = QWidget()
        status_bar.setStyleSheet("""
            QWidget {
                background-color: #2b2b2b;
                border-top: 1px solid #3d3d3d;
            }
        """)
        status_layout = QHBoxLayout(status_bar)
        status_layout.setContentsMargins(12, 8, 12, 8)
        
        self.status_label = QLabel("No comics loaded")
        self.status_label.setStyleSheet("color: #808080; font-size: 12px;")
        status_layout.addWidget(self.status_label)
        
        layout.addWidget(status_bar)

    def load_folder(self, path: Path):
        """Load comics from a folder."""
        self.status_label.setText("Scanning...")
        self.table.model.removeRows(0, self.table.model.rowCount())
        
        self.worker = ScanWorker(path)
        self.worker.finished.connect(self._on_scan_complete)
        self.worker.progress.connect(lambda p: self.status_label.setText(f"Scanning: {p}"))
        self.worker.start()

    def _on_scan_complete(self, comics: list[Comic]):
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
                QStandardItem(comic.status)
            ]
            for item in row:
                item.setEditable(False)
            self.table.model.appendRow(row)

    def _on_enrich(self):
        """Enrich comics from Comic Vine."""
        if not self.config or not self.config.api_key:
            self.status_label.setText("Error: No API key configured")
            return

        self.status_label.setText("Enriching from Comic Vine...")
        self.enrich_btn.setEnabled(False)

        self.enrich_worker = EnrichWorker(self.comics, self.config.api_key)
        self.enrich_worker.finished.connect(self._on_enrich_complete)
        self.enrich_worker.error.connect(
            lambda msg: self.status_label.setText(f"Error: {msg}")
        )
        self.enrich_worker.progress.connect(
            lambda cur, tot: self.status_label.setText(f"Enriching: {cur}/{tot}")
        )
        self.enrich_worker.start()

    def _on_enrich_complete(self, comics: list[Comic], error_occurred: bool):
        """Handle enrich completion."""
        enriched = sum(1 for c in comics if c.has_cv_ids)
        self.comics = comics
        self._populate_table()
        self.enrich_btn.setEnabled(True)
        if not error_occurred:
            self.status_label.setText(
                f"Enriched {enriched}/{len(comics)} comics"
            )

    def _show_context_menu(self, position):
        """Show context menu for table."""
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
        
        selected_rows = self.table.selectionModel().selectedRows()
        if selected_rows:
            add_action = menu.addAction("➕ Add to Reading List")
            add_action.triggered.connect(self._add_to_list)
            menu.addSeparator()
        
        open_action = menu.addAction("🌐 Open CV URL")
        open_action.triggered.connect(self._open_cv_url)
        
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
                    QDesktopServices.openUrl(comic.web_links[0])
