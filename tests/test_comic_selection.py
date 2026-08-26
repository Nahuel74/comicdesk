"""Selection behavior for the comic list."""

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QItemSelection, QItemSelectionModel
from PySide6.QtWidgets import QAbstractItemView, QApplication

from cbl_maker.models import Comic
from cbl_maker.ui.comic_list import ComicList
from cbl_maker.ui.comic_selection import ComicSelection


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def comic_list(qapp):
    widget = ComicList()
    widget._set_comics([Comic(path=Path(f"issue-{number}.cbz")) for number in range(4)])
    yield widget
    widget.close()


def select_rows(widget, first, last=None, command=QItemSelectionModel.Select):
    last = first if last is None else last
    model = widget.table.selectionModel()
    start = widget.table.proxy_model.index(first, 0)
    end = widget.table.proxy_model.index(last, 0)
    if last == first:
        model.select(start, command | QItemSelectionModel.Rows)
    else:
        model.select(QItemSelection(start, end), command | QItemSelectionModel.Rows)


def test_selection_mode_supports_single_multiple_and_range(comic_list):
    assert (comic_list.table.selectionMode()
            == QAbstractItemView.SelectionMode.ExtendedSelection)
    select_rows(comic_list, 1)
    assert comic_list._selected_comics() == [comic_list.comics[1]]
    select_rows(comic_list, 2, command=QItemSelectionModel.Toggle)
    assert comic_list._selected_comics() == [comic_list.comics[1], comic_list.comics[2]]
    select_rows(comic_list, 1, 3, command=QItemSelectionModel.Select)
    assert comic_list._selected_comics() == comic_list.comics[1:4]


def test_select_all_and_clear(comic_list):
    comic_list.table.selectAll()
    assert comic_list._selected_comics() == comic_list.comics
    comic_list.clear_selection_btn.click()
    assert comic_list._selected_comics() == []
    assert not comic_list.add_selected_btn.isEnabled()


def test_add_selected_emits_exact_selected_list(comic_list):
    emitted = []
    comic_list.comics_selected.connect(emitted.append)
    select_rows(comic_list, 0)
    select_rows(comic_list, 2, command=QItemSelectionModel.Toggle)
    comic_list.add_selected_btn.click()
    assert emitted == [[comic_list.comics[0], comic_list.comics[2]]]


def test_selection_state_restores_compatible_comics():
    state = ComicSelection()
    original = [Comic(path=Path("a.cbz")), Comic(path=Path("b.cbz"))]
    state.remember([original[1]])
    refreshed = [Comic(path=Path("b.cbz")), Comic(path=Path("missing.cbz"))]
    assert state.restore(refreshed) == [refreshed[0]]
    assert state.contains(refreshed[0])
