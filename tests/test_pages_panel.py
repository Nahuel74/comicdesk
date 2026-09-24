"""Offscreen tests for the Pages panel."""

import os
import zipfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from comicdesk.models import Comic
from comicdesk.ui.pages_panel import PagesPanel


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


def _make_cbz(path: Path, names: list[str]) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("ComicInfo.xml", b"<ComicInfo><PageCount>2</PageCount></ComicInfo>")
        for name in names:
            archive.writestr(name, b"x")


def test_remove_button_disabled_without_page_selection(qapp, tmp_path):
    path = tmp_path / "book.cbz"
    _make_cbz(path, ["a.jpg", "b.jpg"])
    comic = Comic(path, series_name="Series", issue_number="1")
    panel = PagesPanel()
    panel.set_comics([comic])
    panel._set_comic(comic)
    panel._page_names = ["a.jpg", "b.jpg"]
    for name in panel._page_names:
        panel.page_list.addItem(name)
    panel.page_list.clearSelection()
    panel._update_actions()

    assert panel.remove_button.isEnabled() is False
    panel.shutdown_workers()


def test_confirm_remove_invokes_service(qapp, tmp_path, monkeypatch):
    path = tmp_path / "book.cbz"
    _make_cbz(path, ["a.jpg", "b.jpg", "extra.jpg"])
    comic = Comic(path)
    panel = PagesPanel()
    panel.set_comics([comic])
    panel._set_comic(comic)
    panel._page_names = ["a.jpg", "b.jpg", "extra.jpg"]
    for name in panel._page_names:
        panel.page_list.addItem(name)
    panel.page_list.item(2).setSelected(True)
    calls = []

    def fake_remove(archive_path, names):
        calls.append((Path(archive_path), set(names)))
        return archive_path

    monkeypatch.setattr(
        "comicdesk.ui.pages_workers.remove_image_pages",
        fake_remove,
    )
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )

    panel._on_remove_pages()
    while panel._remove_worker is not None and panel._remove_worker.isRunning():
        qapp.processEvents()

    assert calls == [(path, {"extra.jpg"})]
    panel.shutdown_workers()


def test_cancel_does_not_invoke_service(qapp, tmp_path, monkeypatch):
    path = tmp_path / "book.cbz"
    _make_cbz(path, ["a.jpg", "b.jpg", "extra.jpg"])
    comic = Comic(path)
    panel = PagesPanel()
    panel._set_comic(comic)
    panel._page_names = ["a.jpg", "b.jpg", "extra.jpg"]
    for name in panel._page_names:
        panel.page_list.addItem(name)
    panel.page_list.item(2).setSelected(True)
    calls = []

    monkeypatch.setattr(
        "comicdesk.ui.pages_workers.remove_image_pages",
        lambda *args, **kwargs: calls.append(args) or args[0],
    )
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.No,
    )

    panel._on_remove_pages()

    assert calls == []
    panel.shutdown_workers()


def test_selection_starts_preview_worker(qapp, tmp_path, monkeypatch):
    path = tmp_path / "book.cbz"
    _make_cbz(path, ["a.jpg"])
    comic = Comic(path)
    panel = PagesPanel()
    panel._set_comic(comic)
    panel._page_names = ["a.jpg"]
    panel.page_list.addItem("a.jpg")
    captured = []

    class SpyWorker:
        def __init__(self, archive_path, member_name, token=0):
            captured.append(member_name)

        def start(self):
            return None

        def cancel(self):
            return None

        def isRunning(self):
            return False

        finished = object()
        error = object()

    monkeypatch.setattr("comicdesk.ui.pages_panel.PagesPreviewWorker", SpyWorker)
    panel.page_list.setCurrentRow(0)

    assert captured == ["a.jpg"]
    panel.shutdown_workers()


def test_auto_clean_folder_invokes_detected_names(qapp, tmp_path, monkeypatch):
    clean_path = tmp_path / "clean.cbz"
    junk_path = tmp_path / "junk.cbz"
    _make_cbz(clean_path, ["001.jpg", "002.jpg"])
    _make_cbz(junk_path, ["001.jpg", "002.jpg", "random.jpg"])
    panel = PagesPanel()
    panel._available_comics = [Comic(clean_path), Comic(junk_path)]
    panel._update_actions()
    calls = []

    def fake_remove(archive_path, names):
        calls.append((Path(archive_path), set(names)))
        return archive_path

    monkeypatch.setattr("comicdesk.ui.pages_workers.remove_image_pages", fake_remove)
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )

    panel._on_auto_clean_folder()
    while panel._folder_clean_worker is not None and panel._folder_clean_worker.isRunning():
        qapp.processEvents()

    assert calls == [(junk_path, {"random.jpg"})]
    panel.shutdown_workers()


def test_auto_clean_cancel_does_not_write(qapp, tmp_path, monkeypatch):
    path = tmp_path / "junk.cbz"
    _make_cbz(path, ["001.jpg", "002.jpg", "random.jpg"])
    panel = PagesPanel()
    panel._available_comics = [Comic(path)]
    panel._update_actions()
    calls = []

    monkeypatch.setattr(
        "comicdesk.ui.pages_workers.remove_image_pages",
        lambda *args, **kwargs: calls.append(args) or args[0],
    )
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.No,
    )

    panel._on_auto_clean_folder()

    assert calls == []
    panel.shutdown_workers()


def test_rename_pages_starts_worker(qapp, tmp_path, monkeypatch):
    path = tmp_path / "book.cbz"
    _make_cbz(path, ["001.jpg"])
    comic = Comic(path, series_name="S", issue_number="1")
    panel = PagesPanel()
    panel._available_comics = [comic]
    panel._update_actions()
    started = []

    class _FakeSignal:
        def connect(self, _callback):
            return None

    class SpyRenameWorker:
        progress = _FakeSignal()
        finished = _FakeSignal()
        error = _FakeSignal()

        def __init__(self, rows, token=0):
            started.append(rows)

        def start(self):
            return None

        def cancel(self):
            return None

        def isRunning(self):
            return False

        def deleteLater(self):
            return None

    class SpyDialog:
        @staticmethod
        def exec():
            return QDialog.DialogCode.Accepted

        @staticmethod
        def template_text():
            return "{Page}"

        @staticmethod
        def issue_pad_width():
            return 0

        @staticmethod
        def page_pad_width():
            return 2

        @staticmethod
        def plan_rows():
            from comicdesk.utils.page_rename_template import RenamePageMemberRow
            from comicdesk.utils.rename_template import RenameRowStatus

            return [
                RenamePageMemberRow(
                    comic=comic,
                    old_name="001.jpg",
                    proposed_name="01.jpg",
                    status=RenameRowStatus.OK,
                )
            ]

    monkeypatch.setattr(
        "comicdesk.ui.pages_panel.RenamePagesDialog",
        lambda *args, **kwargs: SpyDialog(),
    )
    monkeypatch.setattr("comicdesk.ui.pages_panel.PagesRenameWorker", SpyRenameWorker)

    panel._on_rename_pages()

    assert len(started) == 1
    assert started[0][0].proposed_name == "01.jpg"
    panel.shutdown_workers()
