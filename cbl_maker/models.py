"""Data models for CBL Maker."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class Comic:
    """Comic metadata extracted from CBZ file."""
    path: Path
    series_name: str = ""
    volume: str = ""
    issue_number: str = ""
    year: str = ""
    web_links: list[str] = field(default_factory=list)
    cv_series_id: Optional[str] = None
    cv_issue_id: Optional[str] = None

    @property
    def has_cv_ids(self) -> bool:
        """Check if Comic Vine IDs are present."""
        return self.cv_series_id is not None and self.cv_issue_id is not None

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
