"""Background workers for library scan and bulk file rename."""

import os
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from comicdesk.models import Comic
from comicdesk.services.comic_archive import scan_comics
from comicdesk.utils.rename_template import (
    RenameFolderPlanRow,
    RenamePlanRow,
    RenameRowStatus,
)


@dataclass
class RenameResult:
    """Outcome of renaming one CBZ file on disk."""

    comic: Comic
    old_path: Path
    new_path: Path | None
    error: str = ""


@dataclass
class FolderRenameResult:
    """Outcome of renaming one series folder on disk."""

    row: RenameFolderPlanRow
    folder_new: Path | None
    library_root_old: Path | None = None
    library_root_new: Path | None = None
    error: str = ""


class FolderRenameWorker(QThread):
    """Rename series folders and update comic paths under each renamed tree."""

    progress = Signal(int, int, str)
    finished = Signal(list)

    def __init__(
        self,
        rows: list[RenameFolderPlanRow],
        library_root: Path,
    ):
        super().__init__()
        self.rows = [row for row in rows if row.status == RenameRowStatus.OK]
        self.library_root = Path(library_root).resolve()
        self._cancelled = False

    def run(self):
        results: list[FolderRenameResult] = []
        total = len(self.rows)
        staged: list[tuple[RenameFolderPlanRow, Path]] = []

        for index, row in enumerate(self.rows):
            if self._cancelled:
                for pending_row, pending_temp in staged:
                    self._restore_temp(pending_row, pending_temp, results)
                break
            old_folder = row.folder_old
            temp_path = old_folder.with_name(
                f".comicdesk-folder-rename-{index}-{old_folder.name}"
            )
            try:
                old_folder.rename(temp_path)
                staged.append((row, temp_path))
            except OSError as exc:
                results.append(
                    FolderRenameResult(row, None, error=str(exc))
                )
            self.progress.emit(index + 1, total, old_folder.name)

        root_old = self.library_root

        for index, (row, temp_path) in enumerate(staged):
            if self._cancelled:
                self._restore_temp(row, temp_path, results)
                continue
            proposed = row.folder_new
            if proposed is None:
                self._restore_temp(row, temp_path, results)
                continue
            try:
                temp_path.rename(proposed)
                old_folder = row.folder_old.resolve()
                prefix_old = str(old_folder)
                prefix_new = str(proposed.resolve())
                for comic in row.comics:
                    path_str = str(comic.path.resolve())
                    if path_str == prefix_old or path_str.startswith(prefix_old + os.sep):
                        suffix = path_str[len(prefix_old) :]
                        comic.path = Path(prefix_new + suffix)
                lib_old = root_old if old_folder == root_old else None
                lib_new = proposed.resolve() if old_folder == root_old else None
                results.append(
                    FolderRenameResult(
                        row,
                        proposed,
                        library_root_old=lib_old,
                        library_root_new=lib_new,
                    )
                )
            except OSError as exc:
                results.append(FolderRenameResult(row, None, error=str(exc)))
                self._restore_temp(row, temp_path, results)
            self.progress.emit(index + 1, total, proposed.name)

        self.finished.emit(results)

    def _restore_temp(
        self,
        row: RenameFolderPlanRow,
        temp_path: Path,
        results: list[FolderRenameResult],
    ):
        if not temp_path.exists():
            return
        try:
            temp_path.rename(row.folder_old)
        except OSError as exc:
            results.append(
                FolderRenameResult(row, None, error=f"Restore failed: {exc}")
            )

    def cancel(self):
        self._cancelled = True


class RenameWorker(QThread):
    """Rename CBZ files on disk using a two-phase temp rename for batch safety."""

    progress = Signal(int, int, str)
    finished = Signal(list)

    def __init__(self, rows: list[RenamePlanRow]):
        super().__init__()
        self.rows = [row for row in rows if row.status == RenameRowStatus.OK]
        self._cancelled = False

    def run(self):
        results: list[RenameResult] = []
        total = len(self.rows)
        staged: list[tuple[RenamePlanRow, Path]] = []

        for index, row in enumerate(self.rows):
            if self._cancelled:
                for pending_row, pending_temp in staged:
                    self._restore_temp(pending_row, pending_temp, results)
                break
            temp_path = row.old_path.with_name(f".comicdesk-rename-{index}-{row.old_path.name}")
            try:
                row.old_path.rename(temp_path)
                staged.append((row, temp_path))
            except OSError as exc:
                results.append(
                    RenameResult(row.comic, row.old_path, None, str(exc))
                )
            self.progress.emit(index + 1, total, row.old_path.name)

        for index, (row, temp_path) in enumerate(staged):
            if self._cancelled:
                self._restore_temp(row, temp_path, results)
                continue
            proposed = row.proposed_path
            if proposed is None:
                self._restore_temp(row, temp_path, results)
                continue
            try:
                temp_path.rename(proposed)
                results.append(RenameResult(row.comic, row.old_path, proposed, ""))
            except OSError as exc:
                results.append(RenameResult(row.comic, row.old_path, None, str(exc)))
                self._restore_temp(row, temp_path, results)
            self.progress.emit(index + 1, total, proposed.name)

        self.finished.emit(results)

    def _restore_temp(self, row: RenamePlanRow, temp_path: Path, results: list[RenameResult]):
        if not temp_path.exists():
            return
        try:
            temp_path.rename(row.old_path)
        except OSError as exc:
            results.append(
                RenameResult(row.comic, row.old_path, None, f"Restore failed: {exc}")
            )

    def cancel(self):
        self._cancelled = True


class ScanWorker(QThread):
    finished = Signal(list)
    progress = Signal(int, int, str)
    error = Signal(str)

    def __init__(self, path: Path, recursive=True):
        super().__init__()
        self.path, self.recursive, self._cancelled = path, recursive, False

    def run(self):
        comics = scan_comics(
            self.path,
            self.recursive,
            progress=lambda current, total, name: self.progress.emit(current, total, name),
            on_error=self.error.emit,
            cancelled=lambda: self._cancelled,
        )
        self.finished.emit(comics)

    def cancel(self):
        self._cancelled = True
