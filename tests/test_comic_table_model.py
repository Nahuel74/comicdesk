"""Tests for the comic table and its reading-list indicator."""

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from comicdesk.models import Comic, ReadingList
from comicdesk.ui.comic_table_model import ComicFilterProxyModel, ComicTableModel


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


def _comic(name, **kwargs):
    return Comic(path=Path(name), series_name="Series", issue_number="1", **kwargs)


def test_reading_list_is_last_column_and_status_is_unchanged(qapp):
    comic = _comic("issue.cbz", cv_series_id="series-1", cv_issue_id="issue-1")
    model = ComicTableModel([comic])

    assert model.columnCount() == len(ComicTableModel.HEADERS)
    assert model.headerData(5, Qt.Horizontal) == "Status"
    assert model.headerData(6, Qt.Horizontal) == "Reading list"
    assert model.data(model.index(0, 5)) == "✅"
    assert model.data(model.index(0, 6)) == "—"
    assert model.data(model.index(0, 6), Qt.ToolTipRole) == "Not in reading list"


def test_indicator_marks_present_and_absent_comics(qapp):
    present = _comic("present.cbz")
    absent = _comic("absent.cbz")
    reading_list = ReadingList("Picks", [Comic(path=present.path)])
    model = ComicTableModel([present, absent], reading_list=reading_list)

    indicator_column = ComicTableModel.HEADERS.index("Reading list")
    assert [model.data(model.index(row, indicator_column)) for row in range(2)] == [
        "✅", "—"
    ]
    assert model.data(model.index(0, indicator_column), Qt.ToolTipRole) == (
        "In reading list"
    )


def test_indicator_updates_after_in_place_reading_list_change(qapp):
    first = _comic("first.cbz")
    second = _comic("second.cbz")
    reading_list = ReadingList("Picks", [Comic(path=first.path)])
    model = ComicTableModel([first, second], reading_list=reading_list)
    changes = []
    model.dataChanged.connect(
        lambda top, bottom, roles: changes.append(
            (top.row(), bottom.row(), top.column(), list(roles))
        )
    )

    reading_list.comics.append(Comic(path=second.path))
    model.set_reading_list(reading_list)

    indicator_column = ComicTableModel.HEADERS.index("Reading list")
    assert model.data(model.index(1, indicator_column)) == "✅"
    assert changes == [(1, 1, indicator_column, [Qt.DisplayRole, Qt.EditRole, Qt.ToolTipRole])]


def test_membership_uses_stable_identity_not_object_identity(qapp):
    listed_by_ids = Comic(
        path=Path(), series_name="Other", issue_number="9",
        cv_series_id="SERIES-7", cv_issue_id="ISSUE-8",
    )
    local_comic = Comic(
        path=Path("downloaded.cbz"), series_name="Current", issue_number="1",
        cv_series_id="series-7", cv_issue_id="issue-8",
    )
    model = ComicTableModel([local_comic], reading_list=ReadingList("IDs", [listed_by_ids]))
    assert model.data(model.index(0, 6)) == "✅"

    listed_by_fields = Comic(path=Path(), series_name="Saga", volume="2", issue_number="3")
    local_copy = Comic(
        path=Path("another.cbz"), series_name=" saga ", volume="2", issue_number="3"
    )
    model.set_comics([local_copy])
    model.set_reading_list(ReadingList("Fields", [listed_by_fields]))
    assert model.data(model.index(0, 6)) == "✅"


def test_status_and_text_filters_are_not_affected_by_indicator(qapp):
    enriched = _comic("enriched.cbz", cv_series_id="s", cv_issue_id="i")
    partial = _comic("partial.cbz", cv_series_id="s")
    pending = _comic("pending.cbz", title="Unique title")
    source = ComicTableModel([enriched, partial, pending])
    proxy = ComicFilterProxyModel()
    proxy.setSourceModel(source)

    proxy.set_status(proxy.STATUS_ENRICHED)
    assert proxy.rowCount() == 1
    assert proxy.data(proxy.index(0, 5)) == "✅"
    proxy.set_status(proxy.STATUS_PARTIAL)
    assert proxy.rowCount() == 1
    assert proxy.data(proxy.index(0, 5)) == "⚠️"
    proxy.set_status(proxy.STATUS_PENDING)
    proxy.set_query("unique title")
    assert proxy.rowCount() == 1
    assert proxy.data(proxy.index(0, 6)) == "—"
