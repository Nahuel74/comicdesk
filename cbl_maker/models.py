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
        return bool(self.cv_series_id and self.cv_issue_id)

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
    order_direction: str = "asc"

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

    def sort_by(self, criterion: str, direction: str = "asc") -> None:
        """Sort by a supported criterion, keeping missing values at the end."""
        if criterion not in {"manual", "release_date", "series_issue", "volume", "title"}:
            return
        direction = direction if direction in {"asc", "desc"} else "asc"
        self.ordered_by = criterion
        self.order_direction = direction
        if criterion == "manual":
            return

        def value(comic):
            if criterion == "release_date":
                return comic.release_date
            if criterion == "series_issue":
                return (comic.series_name or "", comic.issue_number or "")
            if criterion == "volume":
                return comic.volume or ""
            return comic.title or ""

        def is_missing(comic):
            item = value(comic)
            if criterion == "series_issue":
                return not item[0] and not item[1]
            return item is None or item == ""

        present = [comic for comic in self.comics if not is_missing(comic)]
        missing = [comic for comic in self.comics if is_missing(comic)]
        present.sort(key=value, reverse=direction == "desc")
        self.comics[:] = present + missing

    def move_comic(self, comic: Comic, direction: int) -> None:
        """Move comic up (-1) or down (+1) in list."""
        if direction not in (-1, 1):
            return
        try:
            idx = self.comics.index(comic)
            new_idx = max(0, min(len(self.comics) - 1, idx + direction))
            if new_idx == idx:
                return
            self.comics.pop(idx)
            self.comics.insert(new_idx, comic)
            self.ordered_by = "manual"
            self.order_direction = "asc"
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
