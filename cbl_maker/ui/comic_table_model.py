"""Qt models used by the comic list."""

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, QSortFilterProxyModel

from cbl_maker.models import Comic


class ComicTableModel(QAbstractTableModel):
    """Table model backed by a list of Comic objects."""

    HEADERS = ["File", "Series", "Number", "Volume", "Year", "Status"]
    COMIC_ROLE = Qt.UserRole + 1

    def __init__(self, comics=None, parent=None):
        super().__init__(parent)
        self.comics = list(comics or [])

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.comics)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.HEADERS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.HEADERS[section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self.comics)):
            return None
        comic = self.comics[index.row()]
        values = (comic.path.name, comic.series_name, comic.issue_number,
                  comic.volume, comic.year, comic.status)
        if role == self.COMIC_ROLE:
            return comic
        if role in (Qt.DisplayRole, Qt.EditRole):
            return values[index.column()]
        if role == Qt.ToolTipRole:
            return str(values[index.column()])
        return None

    def set_comics(self, comics):
        self.beginResetModel()
        self.comics = list(comics)
        self.endResetModel()

    def comic_at(self, row):
        return self.comics[row] if 0 <= row < len(self.comics) else None


class ComicFilterProxyModel(QSortFilterProxyModel):
    """Case-insensitive search and status filtering without changing source data."""

    STATUS_ALL = "all"
    STATUS_ENRICHED = "enriched"
    STATUS_PARTIAL = "partial"
    STATUS_PENDING = "pending"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._query = ""
        self._status = self.STATUS_ALL
        self.setFilterCaseSensitivity(Qt.CaseInsensitive)

    def set_query(self, query):
        self._query = (query or "").strip().casefold()
        self.invalidateFilter()

    set_filter_text = set_query

    def set_status(self, status):
        self._status = status or self.STATUS_ALL
        self.invalidateFilter()

    set_status_filter = set_status

    def filterAcceptsRow(self, source_row, source_parent):
        model = self.sourceModel()
        comic = model.comic_at(source_row) if model else None
        if comic is None:
            return False
        if self._status == self.STATUS_ENRICHED and not comic.has_cv_ids:
            return False
        if self._status == self.STATUS_PARTIAL and not (
                (comic.cv_series_id or comic.cv_issue_id) and not comic.has_cv_ids):
            return False
        if self._status == self.STATUS_PENDING and (comic.cv_series_id or comic.cv_issue_id):
            return False
        if not self._query:
            return True
        searchable = " ".join((comic.path.name, comic.series_name, comic.title,
                               comic.issue_number, comic.volume, comic.year)).casefold()
        return self._query in searchable
