"""Browse issue image pages and remove unrelated archive members."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from comicdesk.config import Config
from comicdesk.models import Comic
from comicdesk.services.comic_pages import detect_extraneous_image_pages, list_image_pages
from comicdesk.ui.rename_pages_dialog import RenamePagesDialog
from comicdesk.utils.rename_template import RenameRowStatus
from comicdesk.ui.pages_workers import (
    PagesFolderCleanWorker,
    PagesListWorker,
    PagesPreviewWorker,
    PagesRemoveWorker,
    PagesRenameWorker,
    _log_name_sample,
)
from comicdesk.ui.theme import SPACING, button_stylesheet, muted_label_stylesheet

logger = logging.getLogger(__name__)

WORKER_JOIN_TIMEOUT_MS = 5000
PREVIEW_MAX_SIZE = 480
_CONFIRM_LIST_MAX_LINES = 40


class PagesPanel(QWidget):
    """Issue page list and removal controls for the Pages workflow."""

    status_message = Signal(str)
    pages_removed = Signal(object, object, str)  # comic, saved Path, previous path str
    pages_renamed = Signal(object)  # list[tuple[Comic, Path, str previous]]

    def __init__(self, config: Config | None = None, parent=None):
        super().__init__(parent)
        self._config = config
        self._theme = "dark"
        self._available_comics: list[Comic] = []
        self._library_selection: list[Comic] = []
        self._metadata_for_template: Callable[[Comic], Comic | None] | None = None
        self.comic: Comic | None = None
        self._path_key = ""
        self._request_token = 0
        self._list_worker: PagesListWorker | None = None
        self._remove_worker: PagesRemoveWorker | None = None
        self._folder_clean_worker: PagesFolderCleanWorker | None = None
        self._rename_worker: PagesRenameWorker | None = None
        self._preview_worker: PagesPreviewWorker | None = None
        self._preview_token = 0
        self._page_names: list[str] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACING["lg"], SPACING["md"], SPACING["lg"], SPACING["lg"])
        layout.setSpacing(SPACING["md"])

        splitter = QSplitter(Qt.Orientation.Horizontal)
        issue_column = QVBoxLayout()
        issue_host = QWidget()
        issue_host.setLayout(issue_column)
        issue_label = QLabel("Issues in folder")
        issue_label.setStyleSheet(muted_label_stylesheet(self._theme))
        issue_column.addWidget(issue_label)
        self.issue_list = QListWidget()
        self.issue_list.currentRowChanged.connect(self._issue_changed)
        issue_column.addWidget(self.issue_list, 1)

        page_column = QVBoxLayout()
        page_host = QWidget()
        page_host.setLayout(page_column)
        page_label = QLabel("Image pages (archive member names)")
        page_label.setStyleSheet(muted_label_stylesheet(self._theme))
        page_column.addWidget(page_label)
        self.page_list = QListWidget()
        self.page_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.page_list.itemSelectionChanged.connect(self._update_actions)
        self.page_list.currentRowChanged.connect(self._preview_current_page)
        page_column.addWidget(self.page_list, 1)

        preview_column = QVBoxLayout()
        preview_host = QWidget()
        preview_host.setLayout(preview_column)
        preview_label = QLabel("Preview")
        preview_label.setStyleSheet(muted_label_stylesheet(self._theme))
        preview_column.addWidget(preview_label)
        self.preview_image = QLabel("Select a page to preview")
        self.preview_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_image.setMinimumSize(280, 360)
        self.preview_image.setWordWrap(True)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.preview_image)
        preview_column.addWidget(scroll, 1)
        self.preview_caption = QLabel("")
        self.preview_caption.setStyleSheet(muted_label_stylesheet(self._theme))
        self.preview_caption.setWordWrap(True)
        preview_column.addWidget(self.preview_caption)

        pages_splitter = QSplitter(Qt.Orientation.Horizontal)
        pages_splitter.addWidget(page_host)
        pages_splitter.addWidget(preview_host)
        pages_splitter.setStretchFactor(0, 1)
        pages_splitter.setStretchFactor(1, 2)

        splitter.addWidget(issue_host)
        splitter.addWidget(pages_splitter)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        layout.addWidget(splitter, 1)

        actions = QHBoxLayout()
        self.rename_button = QPushButton("Rename pages…")
        self.rename_button.setToolTip(
            "Rename image members inside each archive using a metadata template "
            "(Library selection if any, otherwise the whole scanned folder)."
        )
        self.rename_button.clicked.connect(self._on_rename_pages)
        self.rename_button.setEnabled(False)
        actions.addWidget(self.rename_button)
        self.auto_clean_button = QPushButton("Auto-clean folder…")
        self.auto_clean_button.setToolTip(
            "Detect and remove likely junk pages by filename across every local "
            "comic in the scanned folder. Permanent; review the list before confirming."
        )
        self.auto_clean_button.clicked.connect(self._on_auto_clean_folder)
        self.auto_clean_button.setEnabled(False)
        actions.addWidget(self.auto_clean_button)
        self.remove_button = QPushButton("Delete selected pages…")
        self.remove_button.setToolTip(
            "Permanently remove the pages selected in the list for the current issue."
        )
        self.remove_button.clicked.connect(self._on_remove_pages)
        self.remove_button.setEnabled(False)
        actions.addWidget(self.remove_button)
        actions.addStretch()
        layout.addLayout(actions)

        self.status_label = QLabel("Select a folder and issue to view pages")
        self.status_label.setStyleSheet(muted_label_stylesheet(self._theme))
        layout.addWidget(self.status_label)

    def apply_theme(self, theme: str) -> None:
        self._theme = theme
        self.remove_button.setStyleSheet(button_stylesheet(theme, variant="primary"))
        self.auto_clean_button.setStyleSheet(button_stylesheet(theme))
        self.rename_button.setStyleSheet(button_stylesheet(theme))

    @staticmethod
    def _comic_path_key(comic: Comic | None) -> str:
        raw = getattr(comic, "path", None) if comic is not None else None
        return str(Path(raw)) if raw else ""

    def set_library_selection(self, comics) -> None:
        """Mirror Library table selection for bulk page rename targets."""
        self._library_selection = list(comics or [])
        self._update_actions()

    def set_metadata_for_template(
        self, provider: Callable[[Comic], Comic | None] | None
    ) -> None:
        """Use Metadata tab drafts for {Series} and other comic placeholders."""
        self._metadata_for_template = provider

    def _folder_local_comics(self) -> list[Comic]:
        return [comic for comic in self._available_comics if comic.has_local_file]

    def _rename_targets(self) -> list[Comic]:
        selected = [c for c in self._library_selection if c.has_local_file]
        if selected:
            return selected
        return self._folder_local_comics()

    def _actions_busy(self) -> bool:
        return (
            self._list_worker is not None
            or self._remove_worker is not None
            or self._folder_clean_worker is not None
            or self._rename_worker is not None
        )

    def set_comics(self, comics) -> None:
        """Replace issues from the library scan."""
        current_key = self._path_key
        self._available_comics = list(comics or [])
        self.issue_list.blockSignals(True)
        try:
            self.issue_list.clear()
            for comic in self._available_comics:
                label = comic.path.name
                if comic.series_name or comic.issue_number:
                    detail = comic.series_name or comic.title or ""
                    if comic.issue_number:
                        detail = f"{detail} #{comic.issue_number}".strip()
                    if detail:
                        label = f"{comic.path.name} — {detail}"
                item = QListWidgetItem(label)
                item.setData(Qt.ItemDataRole.UserRole, comic)
                self.issue_list.addItem(item)
            row = -1
            for index in range(self.issue_list.count()):
                item = self.issue_list.item(index)
                if self._comic_path_key(item.data(Qt.ItemDataRole.UserRole)) == current_key:
                    row = index
                    break
            if row >= 0:
                self.issue_list.setCurrentRow(row)
            elif self.issue_list.count():
                self.issue_list.setCurrentRow(0)
            else:
                self._set_comic(None)
        finally:
            self.issue_list.blockSignals(False)
        if self.issue_list.currentRow() < 0:
            self._clear_pages("No comics in this folder", emit=False)
        else:
            self._issue_changed(self.issue_list.currentRow())
        self._update_actions()

    def set_focus_comic(self, comic) -> None:
        """Follow the library table's focused issue."""
        if comic is None:
            return
        key = self._comic_path_key(comic)
        for index in range(self.issue_list.count()):
            item = self.issue_list.item(index)
            if self._comic_path_key(item.data(Qt.ItemDataRole.UserRole)) == key:
                if self.issue_list.currentRow() != index:
                    self.issue_list.setCurrentRow(index)
                return

    def _issue_changed(self, row: int) -> None:
        item = self.issue_list.item(row) if row >= 0 else None
        comic = item.data(Qt.ItemDataRole.UserRole) if item else None
        self._set_comic(comic)
        if comic is None or not comic.has_local_file:
            self._clear_pages("Select an issue with a local file", emit=False)
            return
        self._load_pages(comic)

    def _set_comic(self, comic: Comic | None) -> None:
        self.comic = comic
        self._path_key = self._comic_path_key(comic)

    def _load_pages(self, comic: Comic) -> None:
        self._stop_list_worker()
        self._stop_preview_worker()
        self._clear_preview("Select a page to preview", emit=False)
        self.page_list.clear()
        self._page_names = []
        self._update_actions()
        self._request_token += 1
        token = self._request_token
        path = Path(comic.path)
        worker = PagesListWorker(path, token=token)
        self._list_worker = worker
        worker.finished.connect(lambda pages, w=worker, t=token: self._pages_loaded(pages, w, t))
        worker.error.connect(lambda msg, w=worker, t=token: self._pages_error(msg, w, t))
        worker.finished.connect(worker.deleteLater)
        worker.error.connect(worker.deleteLater)
        worker.start()
        self._set_status("Loading pages…", emit=False)

    def _pages_loaded(self, pages, worker, token: int) -> None:
        if worker is not self._list_worker or token != self._request_token:
            return
        self._list_worker = None
        self._page_names = list(pages or [])
        self.page_list.clear()
        for name in self._page_names:
            self.page_list.addItem(QListWidgetItem(name))
        if not self._page_names:
            self._set_status("This archive has no image pages", emit=False)
        else:
            self._set_status(f"{len(self._page_names)} image page(s)", emit=False)
        if self.page_list.count():
            self.page_list.setCurrentRow(0)
        self._update_actions()

    def _preview_current_page(self, row: int) -> None:
        if row < 0 or self.comic is None:
            self._clear_preview("Select a page to preview", emit=False)
            return
        item = self.page_list.item(row)
        if item is None:
            self._clear_preview("Select a page to preview", emit=False)
            return
        member_name = item.text()
        self.preview_caption.setText(member_name)
        self._stop_preview_worker()
        self._preview_token += 1
        token = self._preview_token
        path = Path(self.comic.path)
        worker = PagesPreviewWorker(path, member_name, token=token)
        self._preview_worker = worker
        worker.finished.connect(
            lambda data, w=worker, t=token, name=member_name: self._preview_loaded(
                data, w, t, name
            )
        )
        worker.error.connect(
            lambda msg, w=worker, t=token: self._preview_error(msg, w, t)
        )
        worker.finished.connect(worker.deleteLater)
        worker.error.connect(worker.deleteLater)
        worker.start()
        self.preview_image.setText("Loading preview…")

    def _preview_loaded(self, data: bytes, worker, token: int, member_name: str) -> None:
        if worker is not self._preview_worker or token != self._preview_token:
            return
        self._preview_worker = None
        pixmap = QPixmap()
        if not pixmap.loadFromData(data):
            self._clear_preview(f"Unable to decode image: {member_name}", emit=False)
            return
        scaled = pixmap.scaled(
            PREVIEW_MAX_SIZE,
            PREVIEW_MAX_SIZE,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.preview_image.setPixmap(scaled)
        self.preview_image.setText("")
        self.preview_caption.setText(member_name)
        self._update_actions()

    def _preview_error(self, message: str, worker, token: int) -> None:
        if worker is not self._preview_worker or token != self._preview_token:
            return
        self._preview_worker = None
        self._clear_preview(f"Preview failed: {message}", emit=False)
        self._update_actions()

    def _clear_preview(self, message: str, *, emit: bool = True) -> None:
        self.preview_image.clear()
        self.preview_image.setText(message)
        self.preview_caption.setText("")
        if emit:
            self.status_message.emit(message)

    def _pages_error(self, message: str, worker, token: int) -> None:
        if worker is not self._list_worker or token != self._request_token:
            return
        self._list_worker = None
        self._clear_pages(message)

    def _clear_pages(self, message: str, *, emit: bool = True) -> None:
        self._stop_preview_worker()
        self._clear_preview("Select a page to preview", emit=False)
        self.page_list.clear()
        self._page_names = []
        self._update_actions()
        self._set_status(message, emit=emit)

    def _selected_page_names(self) -> list[str]:
        return [item.text() for item in self.page_list.selectedItems()]

    def _update_actions(self) -> None:
        selected = self._selected_page_names()
        busy = self._actions_busy()
        enabled = bool(selected) and not busy and bool(self._page_names)
        self.remove_button.setEnabled(enabled and self._list_worker is None)
        folder_locals = self._folder_local_comics()
        self.auto_clean_button.setEnabled(bool(folder_locals) and not busy)
        rename_targets = self._rename_targets()
        self.rename_button.setEnabled(bool(rename_targets) and not busy)

    def _apply_comic_archive_update(
        self, comic: Comic, saved: Path, previous_path: str
    ) -> None:
        comic.path = saved
        try:
            pages = list_image_pages(saved)
            comic.page_count = str(len(pages))
        except Exception:
            pages = []
        self.pages_removed.emit(comic, saved, previous_path)
        if self.comic is comic and self._comic_path_key(comic) == self._path_key:
            self._page_names = pages
            self.page_list.clear()
            for name in pages:
                self.page_list.addItem(QListWidgetItem(name))
            if self.page_list.count():
                self.page_list.setCurrentRow(0)
            self._set_status(f"{len(pages)} image page(s) in this issue", emit=False)

    def _start_remove(self, names: list[str]) -> None:
        if self.comic is None:
            return
        self._request_token += 1
        token = self._request_token
        path = Path(self.comic.path)
        worker = PagesRemoveWorker(path, names, token=token)
        self._remove_worker = worker
        worker.finished.connect(
            lambda saved, w=worker, t=token: self._remove_finished(saved, w, t)
        )
        worker.error.connect(lambda msg, w=worker, t=token: self._remove_error(msg, w, t))
        worker.finished.connect(worker.deleteLater)
        worker.error.connect(worker.deleteLater)
        worker.start()
        self._update_actions()
        sample = _log_name_sample(names)
        self._set_status(
            f"Deleting {len(names)} page(s) from {path.name}: {sample}…"
        )

    def _plan_folder_clean_jobs(self) -> list[tuple[Comic, list[str]]]:
        jobs: list[tuple[Comic, list[str]]] = []
        for comic in self._folder_local_comics():
            try:
                pages = list_image_pages(comic.path)
            except Exception:
                continue
            candidates = detect_extraneous_image_pages(pages)
            if not candidates:
                continue
            if len(pages) - len(set(candidates)) < 1:
                continue
            jobs.append((comic, candidates))
        return jobs

    @staticmethod
    def _format_clean_confirm_body(jobs: list[tuple[Comic, list[str]]]) -> str:
        issue_count = len(jobs)
        file_count = sum(len(names) for _comic, names in jobs)
        lines: list[str] = []
        for comic, names in jobs:
            lines.append(f"{comic.path.name}:")
            for name in names:
                lines.append(f"  • {name}")
        if len(lines) > _CONFIRM_LIST_MAX_LINES:
            hidden = len(lines) - _CONFIRM_LIST_MAX_LINES
            lines = lines[:_CONFIRM_LIST_MAX_LINES]
            lines.append(f"… and {hidden} more line(s)")
        file_block = "\n".join(lines)
        return (
            "Automatic detection uses filenames only and can remove valid pages "
            "(for example unusually named story art).\n\n"
            "This change is permanent and cannot be undone.\n\n"
            f"{issue_count} issue(s), {file_count} file(s) would be removed:\n\n"
            f"{file_block}"
        )

    def _on_auto_clean_folder(self) -> None:
        if self._folder_clean_worker is not None or self._actions_busy():
            return
        jobs = self._plan_folder_clean_jobs()
        if not jobs:
            QMessageBox.information(
                self,
                "Auto-clean folder",
                "No extra pages were detected by filename heuristics in this folder.",
            )
            return
        answer = QMessageBox.question(
            self,
            "Auto-clean folder",
            self._format_clean_confirm_body(jobs),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._last_clean_issue_count = len(jobs)
        self._last_clean_page_total = sum(len(names) for _comic, names in jobs)
        self._request_token += 1
        token = self._request_token
        worker = PagesFolderCleanWorker(jobs, token=token)
        self._folder_clean_worker = worker
        worker.progress.connect(
            lambda current, total, name, w=worker, t=token: self._folder_clean_progress(
                current, total, name, w, t
            )
        )
        worker.finished.connect(
            lambda results, w=worker, t=token: self._folder_clean_finished(results, w, t)
        )
        worker.error.connect(
            lambda msg, w=worker, t=token: self._folder_clean_error(msg, w, t)
        )
        worker.finished.connect(worker.deleteLater)
        worker.error.connect(worker.deleteLater)
        worker.start()
        self._update_actions()
        self._set_status(
            f"Auto-cleaning {self._last_clean_issue_count} issue(s), "
            f"{self._last_clean_page_total} page(s)…"
        )

    def _folder_clean_progress(
        self, current: int, total: int, detail: str, worker, token: int
    ) -> None:
        if worker is not self._folder_clean_worker or token != self._request_token:
            return
        self._set_status(f"Auto-clean ({current}/{total}) — {detail}")

    def _folder_clean_finished(self, results, worker, token: int) -> None:
        if worker is not self._folder_clean_worker or token != self._request_token:
            return
        self._folder_clean_worker = None
        count = 0
        for comic, saved, previous in results or []:
            self._apply_comic_archive_update(comic, Path(saved), previous)
            count += 1
        page_total = getattr(self, "_last_clean_page_total", 0)
        issue_total = getattr(self, "_last_clean_issue_count", count)
        logger.info(
            "pages_auto_clean_ui_done issues=%d pages=%d",
            count,
            page_total,
        )
        self._set_status(
            f"Auto-clean finished: {count}/{issue_total} issue(s), "
            f"{page_total} page(s) removed"
        )
        self._update_actions()

    def _folder_clean_error(self, message: str, worker, token: int) -> None:
        if worker is not self._folder_clean_worker or token != self._request_token:
            return
        self._folder_clean_worker = None
        self._set_status(f"Auto-clean failed: {message}")
        self._update_actions()

    def _on_rename_pages(self) -> None:
        if self._rename_worker is not None or self._actions_busy():
            return
        targets = self._rename_targets()
        if not targets:
            QMessageBox.information(
                self,
                "Rename pages",
                "No local comic files to rename in the current selection or folder.",
            )
            return
        dialog = RenamePagesDialog(
            targets,
            config=self._config,
            target_count=len(targets),
            theme=self._theme,
            metadata_for=self._metadata_for_template,
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        if self._config is not None:
            self._config.last_rename_page_template = dialog.template_text()
            self._config.rename_issue_pad_width = dialog.issue_pad_width()
            self._config.rename_page_pad_width = dialog.page_pad_width()
            self._config.save()
        rows = dialog.plan_rows()
        ok_rows = sum(1 for row in rows if row.status == RenameRowStatus.OK)
        archive_count = len({id(row.comic) for row in rows if row.status == RenameRowStatus.OK})
        self._request_token += 1
        token = self._request_token
        worker = PagesRenameWorker(rows, token=token)
        self._rename_worker = worker
        worker.progress.connect(
            lambda current, total, name, w=worker, t=token: self._rename_progress(
                current, total, name, w, t
            )
        )
        worker.finished.connect(
            lambda results, w=worker, t=token: self._rename_finished(results, w, t)
        )
        worker.error.connect(
            lambda msg, w=worker, t=token: self._rename_error(msg, w, t)
        )
        worker.finished.connect(worker.deleteLater)
        worker.error.connect(worker.deleteLater)
        worker.start()
        self._update_actions()
        self._set_status(
            f"Renaming {ok_rows} page(s) across {archive_count} archive(s)…"
        )

    def _rename_progress(
        self, current: int, total: int, detail: str, worker, token: int
    ) -> None:
        if worker is not self._rename_worker or token != self._request_token:
            return
        self._set_status(f"Rename pages ({current}/{total}) — {detail}")

    def _rename_finished(self, results, worker, token: int) -> None:
        if worker is not self._rename_worker or token != self._request_token:
            return
        self._rename_worker = None
        payload: list[tuple[Comic, Path, str]] = []
        for comic, saved, previous in results or []:
            saved_path = Path(saved)
            comic.path = saved_path
            if self.comic is comic:
                self._path_key = self._comic_path_key(comic)
            payload.append((comic, saved_path, previous))
        if payload:
            self.pages_renamed.emit(payload)
        page_total = len(worker.rows) if worker is not None else 0
        logger.info(
            "pages_rename_ui_done archives=%d pages=%d",
            len(payload),
            page_total,
        )
        self._set_status(
            f"Rename finished: {len(payload)} archive(s), {page_total} page(s) updated"
        )
        if self.comic is not None and payload:
            for comic, saved, _previous in payload:
                if comic is self.comic:
                    self._load_pages(comic)
                    break
        self._update_actions()

    def _rename_error(self, message: str, worker, token: int) -> None:
        if worker is not self._rename_worker or token != self._request_token:
            return
        self._rename_worker = None
        self._set_status(f"Rename pages failed: {message}")
        self._update_actions()

    def _on_remove_pages(self) -> None:
        if self.comic is None or self._remove_worker is not None:
            return
        selected = self._selected_page_names()
        if not selected:
            return
        remaining = len(self._page_names) - len(set(selected))
        if remaining <= 0:
            QMessageBox.warning(
                self,
                "Delete selected pages",
                "At least one image page must remain in the archive.",
            )
            return
        count = len(selected)
        answer = QMessageBox.question(
            self,
            "Delete selected pages",
            f"Delete {count} page(s) from the archive permanently?\n"
            "This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._start_remove(selected)

    def _remove_finished(self, saved_path, worker, token: int) -> None:
        if worker is not self._remove_worker or token != self._request_token:
            return
        self._remove_worker = None
        comic = self.comic
        if comic is None:
            self._update_actions()
            return
        previous_path = str(comic.path)
        saved = Path(saved_path)
        if str(saved) != previous_path:
            self._path_key = self._comic_path_key(comic)
        self._apply_comic_archive_update(comic, saved, previous_path)
        removed = list(worker.names)
        archive = Path(previous_path).name
        message = (
            f"Deleted {len(removed)} page(s) from {archive}: "
            f"{_log_name_sample(removed)} — {len(self._page_names)} page(s) remain"
        )
        if saved.name != archive:
            message = f"{message} (saved as {saved.name})"
        logger.info(
            "pages_remove_ui_done archive=%s removed=%d remain=%d",
            archive,
            len(removed),
            len(self._page_names),
        )
        self._set_status(message)
        self._update_actions()

    def _remove_error(self, message: str, worker, token: int) -> None:
        if worker is not self._remove_worker or token != self._request_token:
            return
        self._remove_worker = None
        self._set_status(f"Remove failed: {message}")
        self._update_actions()

    def _set_status(self, message: str, *, emit: bool = True) -> None:
        self.status_label.setText(message)
        if emit:
            self.status_message.emit(message)

    def _stop_list_worker(self) -> None:
        worker = self._list_worker
        if worker is None:
            return
        worker.cancel()
        if worker.isRunning():
            worker.wait(WORKER_JOIN_TIMEOUT_MS)
        self._list_worker = None

    def _stop_remove_worker(self) -> None:
        worker = self._remove_worker
        if worker is None:
            return
        worker.cancel()
        if worker.isRunning():
            worker.wait(WORKER_JOIN_TIMEOUT_MS)
        self._remove_worker = None

    def _stop_preview_worker(self) -> None:
        worker = self._preview_worker
        if worker is None:
            return
        worker.cancel()
        if worker.isRunning():
            worker.wait(WORKER_JOIN_TIMEOUT_MS)
        self._preview_worker = None

    def _stop_folder_clean_worker(self) -> None:
        worker = self._folder_clean_worker
        if worker is None:
            return
        worker.cancel()
        if worker.isRunning():
            worker.wait(WORKER_JOIN_TIMEOUT_MS)
        self._folder_clean_worker = None

    def _stop_rename_worker(self) -> None:
        worker = self._rename_worker
        if worker is None:
            return
        worker.cancel()
        if worker.isRunning():
            worker.wait(WORKER_JOIN_TIMEOUT_MS)
        self._rename_worker = None

    def shutdown_workers(self) -> None:
        self._stop_list_worker()
        self._stop_remove_worker()
        self._stop_folder_clean_worker()
        self._stop_rename_worker()
        self._stop_preview_worker()
