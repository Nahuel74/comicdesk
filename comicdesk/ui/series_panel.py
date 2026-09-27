"""Series gap view for the Collection area."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from comicdesk.models import Comic
from comicdesk.services.series_gaps import (
    all_missing_issues_as_cbl_books,
    analyze_series_gaps,
)
from comicdesk.ui.theme import button_stylesheet, muted_label_stylesheet, table_stylesheet
from comicdesk.ui.widgets.panel_chrome import PanelChrome


class SeriesPanel(QWidget):
    """Show per-series missing issue numbers from ComicInfo Count."""

    wishlist_requested = Signal(list)
    status_message = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._theme = "dark"
        self._comics: list[Comic] = []
        self._reports: list[SeriesGapReport] = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._chrome = PanelChrome(
            "Series gaps",
            "Missing issue numbers when ComicInfo Count is set on scanned files. "
            "Groups by Comic Vine series ID, or series name and volume year.",
        )
        layout.addWidget(self._chrome)
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self._rebuild)
        self.wishlist_all_btn = QPushButton("Add all missing to wishlist")
        self.wishlist_all_btn.setToolTip(
            "Add every missing issue from all series in the table to Acquire → Wishlist"
        )
        self.wishlist_all_btn.clicked.connect(self._add_all_missing_to_wishlist)
        self._chrome.add_action_widget(self.refresh_btn)
        self._chrome.add_action_widget(self.wishlist_all_btn)
        body = QVBoxLayout()
        body.setContentsMargins(12, 8, 12, 12)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Series", "Owned", "Expected", "Missing", "Series ID"]
        )
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        body.addWidget(self.table, 1)
        self.status_label = QLabel("Scan a folder on Browse to analyze series.")
        body.addWidget(self.status_label)
        body_host = QWidget()
        body_host.setLayout(body)
        layout.addWidget(body_host, 1)
        self.apply_theme(self._theme)

    def set_comics(self, comics: list[Comic]) -> None:
        self._comics = list(comics)
        self._rebuild()

    def _rebuild(self) -> None:
        self._reports = analyze_series_gaps(self._comics)
        self.table.setRowCount(len(self._reports))
        for row, report in enumerate(self._reports):
            self.table.setItem(row, 0, QTableWidgetItem(report.key.label()))
            self.table.setItem(row, 1, QTableWidgetItem(str(len(report.present_numbers))))
            expected = str(report.expected_count) if report.expected_count else "—"
            self.table.setItem(row, 2, QTableWidgetItem(expected))
            self.table.setItem(row, 3, QTableWidgetItem(str(len(report.missing_numbers))))
            self.table.setItem(row, 4, QTableWidgetItem(report.key.cv_series_id or "—"))
        gaps = sum(1 for report in self._reports if report.has_gaps)
        missing_total = sum(len(r.missing_numbers) for r in self._reports)
        self.status_label.setText(
            f"{len(self._reports)} series · {gaps} with gaps · {missing_total} missing issue(s)"
        )
        has_gaps = missing_total > 0
        self.wishlist_all_btn.setEnabled(has_gaps)
        if has_gaps and self.table.currentRow() < 0:
            for row, report in enumerate(self._reports):
                if report.has_gaps:
                    self.table.selectRow(row)
                    break

    def _add_all_missing_to_wishlist(self) -> None:
        books = all_missing_issues_as_cbl_books(self._reports)
        if not books:
            QMessageBox.information(
                self,
                "Wishlist",
                "No missing issues to add. Set ComicInfo Count on your files and scan "
                "the library on Browse first.",
            )
            return
        self.wishlist_requested.emit(books)
        self.status_message.emit(f"Queued {len(books)} missing issue(s) for the wishlist")

    def apply_theme(self, theme: str) -> None:
        self._theme = theme
        self.table.setStyleSheet(table_stylesheet(theme))
        self.status_label.setStyleSheet(muted_label_stylesheet(theme))
        default = button_stylesheet(theme, "default")
        self.refresh_btn.setStyleSheet(default)
        self.wishlist_all_btn.setStyleSheet(default)
