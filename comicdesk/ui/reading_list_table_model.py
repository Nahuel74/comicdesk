"""Table model for comics in the active reading list."""

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal
from PySide6.QtGui import QColor

from comicdesk.models import Comic, ReadingList
from comicdesk.services.cbl_display import comic_release_display


class ReadingListTableModel(QAbstractTableModel):
    """Backed by :class:`ReadingList`; supports internal drag-and-drop reorder."""

    manual_order_changed = Signal()

    COL_NUM = 0
    COL_SERIES = 1
    COL_VOLUME = 2
    COL_ISSUE = 3
    COL_TITLE = 4
    COL_RELEASE = 5
    COL_FILE = 6

    COLUMNS = ("#", "Series", "Volume", "Issue", "Title", "Release Date", "File")

    def __init__(self, parent=None):
        super().__init__(parent)
        self._reading_list: ReadingList | None = None
        self._muted_color: QColor | None = None

    def set_muted_color(self, color: QColor | None) -> None:
        self._muted_color = color

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

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemFlag.ItemIsDropEnabled
        flags = (
            Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsDragEnabled
            | Qt.ItemFlag.ItemIsDropEnabled
        )
        return flags

    def supportedDropActions(self):
        return Qt.DropAction.MoveAction

    def moveRows(
        self,
        source_parent,
        source_row: int,
        count: int,
        destination_parent,
        destination_child: int,
    ) -> bool:
        if (
            self._reading_list is None
            or count != 1
            or source_parent.isValid()
            or destination_parent.isValid()
        ):
            return False
        comics = self._reading_list.comics
        if source_row < 0 or source_row >= len(comics):
            return False
        dest = destination_child
        if dest > source_row:
            dest -= 1
        dest = max(0, min(len(comics) - 1, dest))
        if source_row == dest:
            return False
        if not self.beginMoveRows(
            source_parent, source_row, source_row, destination_parent, destination_child
        ):
            return False
        comic = comics.pop(source_row)
        comics.insert(dest, comic)
        self._reading_list.ordered_by = "manual"
        self._reading_list.order_direction = "asc"
        self.endMoveRows()
        self.manual_order_changed.emit()
        return True

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or self._reading_list is None:
            return None
        comic = self.comic_at(index.row())
        if comic is None:
            return None
        column = index.column()
        virtual = not comic.has_local_file
        if role == Qt.ItemDataRole.DisplayRole:
            if column == self.COL_NUM:
                return str(index.row() + 1)
            if column == self.COL_SERIES:
                return comic.series_name or "—"
            if column == self.COL_VOLUME:
                return comic.volume or "—"
            if column == self.COL_ISSUE:
                return comic.issue_number or "—"
            if column == self.COL_TITLE:
                return comic.title or "—"
            if column == self.COL_RELEASE:
                return comic_release_display(comic)
            if column == self.COL_FILE:
                if comic.has_local_file:
                    return comic.path.name
                return "Not in library"
        if role == Qt.ItemDataRole.ToolTipRole:
            if column == self.COL_SERIES and comic.has_local_file and comic.series_name:
                return str(comic.path)
            if column == self.COL_SERIES and virtual:
                return "Not in library"
            if column == self.COL_FILE and comic.has_local_file:
                return str(comic.path)
            if column == self.COL_FILE and virtual:
                return "No local CBZ file linked"
            if column == self.COL_RELEASE:
                if comic.release_date is not None:
                    return "From ComicInfo release date"
                if comic.year:
                    return "Year only (ComicInfo or CBL); month/day not set"
                if comic.cv_metadata and comic.cv_metadata.cover_date:
                    return "From Comic Vine cover date in CBL metadata"
            if column == self.COL_TITLE and comic.title:
                return comic.title
        if role == Qt.ItemDataRole.ForegroundRole and virtual and self._muted_color is not None:
            if column in (
                self.COL_SERIES,
                self.COL_VOLUME,
                self.COL_ISSUE,
                self.COL_FILE,
            ):
                return self._muted_color
        if role == Qt.ItemDataRole.UserRole:
            return comic
        return None

    def refresh(self) -> None:
        if self._reading_list is None:
            return
        self.beginResetModel()
        self.endResetModel()
