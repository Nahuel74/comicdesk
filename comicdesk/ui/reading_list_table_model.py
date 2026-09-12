"""Table model for comics in the active reading list."""

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt

from comicdesk.models import Comic, ReadingList


class ReadingListTableModel(QAbstractTableModel):
    COLUMNS = ("#", "Series", "Issue", "Volume", "Year", "Status", "File")

    def __init__(self, parent=None):
        super().__init__(parent)
        self._reading_list: ReadingList | None = None

    def set_reading_list(self, reading_list: ReadingList) -> None:
        self.beginResetModel()
        self._reading_list = reading_list
        self.endResetModel()

    def reading_list(self) -> ReadingList | None:
        return self._reading_list

    def comic_at(self, row: int) -> Comic | None:
        if self._reading_list is None or row < 0 or row >= len(self._reading_list.comics):
            return None
        return self._reading_list.comics[row]

    def rowCount(self, parent=QModelIndex()):
        if parent.isValid() or self._reading_list is None:
            return 0
        return len(self._reading_list.comics)

    def columnCount(self, parent=QModelIndex()):
        if parent.isValid():
            return 0
        return len(self.COLUMNS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole or orientation != Qt.Orientation.Horizontal:
            return None
        return self.COLUMNS[section]

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or self._reading_list is None:
            return None
        comic = self.comic_at(index.row())
        if comic is None:
            return None
        column = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            if column == 0:
                return str(index.row() + 1)
            if column == 1:
                return comic.series_name or comic.title or "—"
            if column == 2:
                return comic.issue_number or "—"
            if column == 3:
                return comic.volume or "—"
            if column == 4:
                return comic.year or "—"
            if column == 5:
                return comic.status
            if column == 6:
                return comic.path.name if comic.path else "—"
        if role == Qt.ItemDataRole.UserRole:
            return comic
        return None

    def refresh(self) -> None:
        if self._reading_list is None:
            return
        self.beginResetModel()
        self.endResetModel()
