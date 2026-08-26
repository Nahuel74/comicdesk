"""Data models for CBL Maker."""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class Comic:
    """Comic metadata extracted from CBZ file."""
    path: Path
    title: str = ""
    series_name: str = ""
    volume: str = ""
    issue_number: str = ""
    year: str = ""
    month: str = ""
    day: str = ""
    web_links: list[str] = field(default_factory=list)
    cv_series_id: Optional[str] = None
    cv_issue_id: Optional[str] = None

    @property
    def has_cv_ids(self) -> bool:
        """Check if Comic Vine IDs are present."""
        return self.cv_series_id is not None and self.cv_issue_id is not None

    @property
    def release_date(self):
        """Return release date as datetime or None if year is missing."""
        if not self.year:
            return None
        try:
            from datetime import datetime
            month = int(self.month) if self.month else 1
            day = int(self.day) if self.day else 1
            return datetime(int(self.year), month, day)
        except (ValueError, TypeError):
            return None

    @property
    def status(self) -> str:
        """Get comic status icon."""
        if self.has_cv_ids:
            return "✅"
        if self.cv_series_id or self.cv_issue_id:
            return "⚠️"
        return "❌"


@dataclass
class ReadingList:
    """Comic reading list."""
    name: str
    comics: list[Comic] = field(default_factory=list)
    ordered_by: str = "release_date"  # "release_date" | "manual"

    def add_comic(self, comic: Comic) -> bool:
        """Add comic to list. Returns False if already exists."""
        if any(c.path == comic.path for c in self.comics):
            return False
        self.comics.append(comic)
        return True

    def remove_comic(self, comic: Comic) -> bool:
        """Remove comic from list."""
        initial_len = len(self.comics)
        self.comics = [c for c in self.comics if c.path != comic.path]
        return len(self.comics) < initial_len

    def sort_by(self, criterion: str) -> None:
        """Sort comics by the given criterion."""
        self.ordered_by = criterion

        if criterion == "release_date":
            self.comics.sort(key=lambda c: c.release_date or datetime.min)
        elif criterion == "series_issue":
            self.comics.sort(key=lambda c: (c.series_name, c.issue_number))
        elif criterion == "volume":
            self.comics.sort(key=lambda c: c.volume)
        elif criterion == "title":
            self.comics.sort(key=lambda c: c.title)
        # "manual" = no sort, keep current order

    def move_comic(self, comic: Comic, direction: int) -> None:
        """Move comic up (-1) or down (+1) in list."""
        try:
            idx = self.comics.index(comic)
            new_idx = max(0, min(len(self.comics) - 1, idx + direction))
            self.comics.pop(idx)
            self.comics.insert(new_idx, comic)
        except ValueError:
            pass


@dataclass
class ComicVineIssue:
    """Issue data from Comic Vine API."""
    id: str
    series_id: str
    series_name: str
    volume: str
    issue_number: str
    cover_date: str
    web_url: str
