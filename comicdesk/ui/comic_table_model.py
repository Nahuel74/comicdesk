"""Qt models used by the comic list."""

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, QSortFilterProxyModel

from comicdesk.models import Comic
from comicdesk.services.cbl_reader import _identity, _normal


class ComicTableModel(QAbstractTableModel):
    """Table model backed by a list of Comic objects."""

    HEADERS = ["File", "Series", "Number", "Name", "Volume", "Year", "Reading list"]
    COMIC_ROLE = Qt.UserRole + 1

    def __init__(self, comics=None, parent=None, reading_list=None):
        super().__init__(parent)
        self.comics = list(comics or [])
        self._reading_list_snapshot = self._snapshot_reading_list(reading_list)

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
        values = (
            comic.path.name,
            comic.series_name,
            comic.issue_number,
            comic.title,
            comic.volume,
            comic.year,
            self._reading_list_indicator(comic),
        )
        if role == self.COMIC_ROLE:
            return comic
        if role in (Qt.DisplayRole, Qt.EditRole):
            return values[index.column()]
        if role == Qt.ToolTipRole:
            if index.column() == len(self.HEADERS) - 1:
                return ("In reading list" if values[index.column()] == "✅"
                        else "Not in reading list")
            return str(values[index.column()])
        return None

    def set_comics(self, comics):
        self.beginResetModel()
        self.comics = list(comics)
        self.endResetModel()

    def set_reading_list(self, reading_list):
        """Set the list used by the indicator without resetting table rows."""
        old_snapshot = self._reading_list_snapshot
        old_membership = [self._is_member(comic, old_snapshot)
                          for comic in self.comics]
        self._reading_list_snapshot = self._snapshot_reading_list(reading_list)
        changed_rows = [row for row, comic in enumerate(self.comics)
                        if self._is_member(comic, self._reading_list_snapshot)
                        != old_membership[row]]
        if not changed_rows:
            return
        column = self.HEADERS.index("Reading list")
        start = previous = changed_rows[0]
        for row in changed_rows[1:] + [None]:
            if row is not None and row == previous + 1:
                previous = row
                continue
            self.dataChanged.emit(self.index(start, column),
                                  self.index(previous, column),
                                  [Qt.DisplayRole, Qt.EditRole, Qt.ToolTipRole])
            if row is not None:
                start = previous = row

    update_reading_list = set_reading_list

    @staticmethod
    def _snapshot_reading_list(reading_list):
        """Keep value keys so in-place ReadingList mutations remain observable."""
        if reading_list is None:
            return ()
        snapshot = []
        for comic in getattr(reading_list, "comics", reading_list):
            path = getattr(comic, "path", None)
            cv_issue = _normal(getattr(comic, "cv_issue_id", "") or "")
            cv_series = _normal(getattr(comic, "cv_series_id", "") or "")
            fallback = _identity(getattr(comic, "series_name", "") or "",
                                 getattr(comic, "volume", "") or "",
                                 getattr(comic, "issue_number", "") or "")
            snapshot.append((path, cv_issue, cv_series, fallback))
        return tuple(snapshot)

    @staticmethod
    def _is_local_path(path):
        return path is not None and str(path) not in {"", "."}

    @classmethod
    def _is_member(cls, comic, snapshot):
        path = getattr(comic, "path", None)
        if cls._is_local_path(path):
            for item_path, _, _, _ in snapshot:
                if cls._is_local_path(item_path) and path == item_path:
                    return True

        issue = _normal(getattr(comic, "cv_issue_id", "") or "")
        series_id = _normal(getattr(comic, "cv_series_id", "") or "")
        identity = _identity(getattr(comic, "series_name", "") or "",
                             getattr(comic, "volume", "") or "",
                             getattr(comic, "issue_number", "") or "")
        for _, listed_issue, listed_series, listed_identity in snapshot:
            # This intentionally follows cbl_reader's reconciliation rule:
            # issue IDs are sufficient unless both series IDs are present.
            if issue and listed_issue == issue:
                if not series_id or not listed_series or series_id == listed_series:
                    return True
            if all(identity) and identity == listed_identity and all(listed_identity):
                return True
        return False

    def _reading_list_indicator(self, comic):
        return "✅" if self._is_member(comic, self._reading_list_snapshot) else "—"

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
