"""Table model for CBZ files in the active library folder."""

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt

from comicdesk.models import Comic


class MetadataInstanceModel(QAbstractTableModel):
    COLUMNS = ("File", "Series", "Issue", "Metadata status")

    def __init__(self, parent=None):
        super().__init__(parent)
        self._comics: list[Comic] = []
        self._filter = ""
        self._editing_path = ""

    def set_comics(self, comics: list[Comic]) -> None:
        self.beginResetModel()
        self._comics = list(comics or [])
        self.endResetModel()

    def set_filter(self, text: str) -> None:
        self._filter = (text or "").strip().lower()
        self.beginResetModel()
        self.endResetModel()

    def set_editing_path(self, path: str) -> None:
        """Highlight the row whose file is shown in the metadata editor."""
        new_path = path or ""
        if new_path == self._editing_path:
            return
        self._editing_path = new_path
        if self.rowCount() <= 0:
            return
        top = self.index(0, 0)
        bottom = self.index(self.rowCount() - 1, 0)
        self.dataChanged.emit(top, bottom, [Qt.ItemDataRole.DisplayRole])

    def comic_at(self, row: int) -> Comic | None:
        visible = self._visible_rows()
        if 0 <= row < len(visible):
            return visible[row]
        return None

    def row_for_comic(self, comic: Comic | None) -> int:
        if comic is None:
            return -1
        key = str(comic.path)
        for index, item in enumerate(self._visible_rows()):
            if str(item.path) == key:
                return index
        return -1

    def notify_comic_changed(self, comic: Comic) -> None:
        row = self.row_for_comic(comic)
        if row < 0:
            return
        top_left = self.index(row, 0)
        bottom_right = self.index(row, self.columnCount() - 1)
        self.dataChanged.emit(
            top_left,
            bottom_right,
            [Qt.ItemDataRole.DisplayRole],
        )

    def _visible_rows(self) -> list[Comic]:
        if not self._filter:
            return self._comics
        rows = []
        for comic in self._comics:
            haystack = " ".join(
                [
                    comic.path.name,
                    comic.series_name,
                    comic.title,
                    comic.issue_number,
                ]
            ).lower()
            if self._filter in haystack:
                rows.append(comic)
        return rows

    def rowCount(self, parent=QModelIndex()):
        if parent.isValid():
            return 0
        return len(self._visible_rows())

    def columnCount(self, parent=QModelIndex()):
        if parent.isValid():
            return 0
        return len(self.COLUMNS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole or orientation != Qt.Orientation.Horizontal:
            return None
        return self.COLUMNS[section]

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        comic = self.comic_at(index.row())
        if comic is None:
            return None
        column = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            if column == 0:
                name = comic.path.name
                if self._editing_path and str(comic.path) == self._editing_path:
                    return f"▸ {name}"
                return name
            if column == 1:
                return comic.series_name or comic.title or "—"
            if column == 2:
                return comic.issue_number or "—"
            if column == 3:
                return comic.status
        if role == Qt.ItemDataRole.UserRole:
            return comic
        return None
