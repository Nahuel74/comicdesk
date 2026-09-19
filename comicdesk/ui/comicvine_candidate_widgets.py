"""Shared Comic Vine search result rows and cover loading."""

from __future__ import annotations

import logging

import httpx
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from comicdesk.models import ComicVineIssue, ComicVineVolume
from comicdesk.ui.theme import muted_label_stylesheet

logger = logging.getLogger(__name__)

COVER_WIDTH = 52
COVER_HEIGHT = 78
CANDIDATE_ROW_HEIGHT = 88


class CoverLoader(QThread):
    finished = Signal(bytes, int)
    error = Signal(int)

    def __init__(self, url: str, row: int):
        super().__init__()
        self.url = url
        self.row = row
        self._cancelled = False

    def run(self) -> None:
        if self._cancelled or not self.url:
            return
        try:
            response = httpx.get(
                self.url,
                timeout=20,
                follow_redirects=True,
                headers={"User-Agent": "ComicDesk/1.0"},
            )
            response.raise_for_status()
            if not self._cancelled:
                self.finished.emit(response.content, self.row)
        except Exception:
            logger.debug("cover_load_failed url=%s", self.url, exc_info=True)
            if not self._cancelled:
                self.error.emit(self.row)

    def cancel(self) -> None:
        self._cancelled = True


class CandidateResultRow(QWidget):
    """One search hit with cover art and descriptive text."""

    def __init__(self, headline: str, subtitle: str, detail: str, theme: str, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(10)
        self.cover_label = QLabel("…")
        self.cover_label.setFixedSize(COVER_WIDTH, COVER_HEIGHT)
        self.cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover_label.setStyleSheet(muted_label_stylesheet(theme))
        layout.addWidget(self.cover_label)
        text_column = QVBoxLayout()
        text_column.setSpacing(2)
        self.headline_label = QLabel(headline)
        self.headline_label.setWordWrap(True)
        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setWordWrap(True)
        self.subtitle_label.setStyleSheet(muted_label_stylesheet(theme))
        self.detail_label = QLabel(detail)
        self.detail_label.setWordWrap(True)
        self.detail_label.setStyleSheet(muted_label_stylesheet(theme))
        text_column.addWidget(self.headline_label)
        text_column.addWidget(self.subtitle_label)
        text_column.addWidget(self.detail_label)
        text_column.addStretch()
        layout.addLayout(text_column, 1)

    def set_cover_pixmap(self, pixmap: QPixmap) -> None:
        scaled = pixmap.scaled(
            self.cover_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.cover_label.setPixmap(scaled)
        self.cover_label.setText("")

    def set_cover_failed(self) -> None:
        self.cover_label.setText("—")
        self.cover_label.setPixmap(QPixmap())


def _release_label(issue: ComicVineIssue) -> str:
    store = (issue.store_date or "").strip()
    if store:
        return f"Released: {store[:10]}"
    return ""


def candidate_lines(candidate) -> tuple[str, str, str]:
    if isinstance(candidate, ComicVineIssue):
        series = candidate.series_name or "Unknown series"
        number = candidate.issue_number or "?"
        headline = f"{series} #{number}"
        subtitle = (candidate.name or "").strip() or "—"
        detail = _release_label(candidate)
        if not detail:
            year = candidate.volume_start_year or ""
            if year:
                detail = f"Series started: {year}"
        return headline, subtitle, detail
    if isinstance(candidate, ComicVineVolume):
        headline = candidate.name or "Unknown series"
        subtitle = "Series / volume"
        year = candidate.start_year or ""
        detail = f"Started: {year}" if year else ""
        return headline, subtitle, detail
    name = getattr(candidate, "name", "") or getattr(candidate, "series_name", "")
    return name or "Result", "", ""
