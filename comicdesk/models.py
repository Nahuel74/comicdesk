"""Data models for ComicDesk."""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


@dataclass
class Comic:
    """Comic metadata extracted from a local comic archive."""
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
    cv_metadata: Optional["ComicVineMetadata"] = None
    alternate_series: str = ""
    alternate_number: str = ""
    alternate_count: str = ""
    count: str = ""
    story_arc: str = ""
    story_arc_number: str = ""
    summary: str = ""
    notes: str = ""
    writer: str = ""
    penciller: str = ""
    inker: str = ""
    colorist: str = ""
    letterer: str = ""
    cover_artist: str = ""
    editor: str = ""
    translator: str = ""
    publisher: str = ""
    imprint: str = ""
    genre: str = ""
    tags: str = ""
    page_count: str = ""
    language_iso: str = ""
    format: str = ""
    black_and_white: str = ""
    manga: str = ""
    characters: str = ""
    teams: str = ""
    locations: str = ""
    scan_information: str = ""
    age_rating: str = ""
    community_rating: str = ""
    main_character_or_team: str = ""
    review: str = ""
    series_group: str = ""
    gtin: str = ""
    comicinfo_unknown: list[Any] = field(default_factory=list)

    @property
    def has_cv_ids(self) -> bool:
        """Check if Comic Vine IDs are present."""
        return bool(self.cv_series_id and self.cv_issue_id)

    @property
    def has_local_file(self) -> bool:
        """True when the comic is backed by a scanned local archive path."""
        if self.path is None:
            return False
        text = str(self.path)
        return text not in {"", "."}

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


@dataclass(frozen=True)
class CBLBook:
    """A book reference read from a ComicRack CBL document.

    A CBL contains references, not files.  Keeping this separate from
    :class:`Comic` prevents an import from inventing a local path.
    """
    series_name: str = ""
    volume: str = ""
    issue_number: str = ""
    year: str = ""
    cv_series_id: Optional[str] = None
    cv_issue_id: Optional[str] = None
    position: int = 0
    cv_metadata: Optional["ComicVineMetadata"] = None

    def to_comic(self, path: Optional[Path] = None) -> Comic:
        """Create an importable Comic without contacting Comic Vine."""
        return Comic(
            path=path or Path(),
            series_name=self.series_name,
            volume=self.volume,
            issue_number=self.issue_number,
            year=self.year,
            cv_series_id=self.cv_series_id,
            cv_issue_id=self.cv_issue_id,
            cv_metadata=self.cv_metadata,
        )


@dataclass
class ReadingList:
    """Comic reading list."""
    name: str
    comics: list[Comic] = field(default_factory=list)
    ordered_by: str = "release_date"  # "release_date" | "manual"
    order_direction: str = "asc"

    def add_comic(self, comic: Comic) -> bool:
        """Add comic to list. Returns False if already exists."""
        if any(self._same_comic(existing, comic) for existing in self.comics):
            return False
        self.comics.append(comic)
        return True

    def remove_comic(self, comic: Comic) -> bool:
        """Remove comic from list."""
        initial_len = len(self.comics)
        self.comics = [c for c in self.comics if not self._same_comic(c, comic)]
        return len(self.comics) < initial_len

    @staticmethod
    def _same_comic(left: Comic, right: Comic) -> bool:
        from comicdesk.services.cbl_reader import comic_dedupe_key

        if left.has_local_file and right.has_local_file:
            return left.path == right.path
        return comic_dedupe_key(left) == comic_dedupe_key(right)

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

    def move_comic_to_index(self, from_index: int, to_index: int) -> None:
        """Move a comic from one list index to another."""
        if from_index < 0 or from_index >= len(self.comics):
            return
        to_index = max(0, min(len(self.comics) - 1, to_index))
        if from_index == to_index:
            return
        comic = self.comics.pop(from_index)
        self.comics.insert(to_index, comic)
        self.ordered_by = "manual"
        self.order_direction = "asc"


@dataclass
class ComicVineVolume:
    """Volume/series data from Comic Vine API."""
    id: str
    name: str
    start_year: str = ""
    web_url: str = ""
    count_of_issues: str = ""
    description: str = ""
    publisher: str = ""
    genres: list[str] = field(default_factory=list)
    character_credits: list[str] = field(default_factory=list)
    concept_credits: list[str] = field(default_factory=list)
    location_credits: list[str] = field(default_factory=list)
    person_credits: list[dict[str, str]] = field(default_factory=list)
    team_credits: list[str] = field(default_factory=list)
    age_rating: str = ""
    image_url: str = ""


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
    store_date: str = ""
    name: str = ""
    description: str = ""
    publisher: str = ""
    genres: list[str] = field(default_factory=list)
    character_credits: list[str] = field(default_factory=list)
    concept_credits: list[str] = field(default_factory=list)
    location_credits: list[str] = field(default_factory=list)
    person_credits: list[dict[str, str]] = field(default_factory=list)
    story_arc_credits: list[str] = field(default_factory=list)
    team_credits: list[str] = field(default_factory=list)
    age_rating: str = ""
    volume_start_year: str = ""
    volume_count_of_issues: str = ""
    image_url: str = ""


# ``ComicVineIssue`` is the API-facing name retained for compatibility.  The
# metadata stored on a Comic uses the more general domain name because it can
# be enriched independently of the legacy ID fields.
ComicVineMetadata = ComicVineIssue
