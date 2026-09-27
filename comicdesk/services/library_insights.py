"""Aggregate local library statistics from scanned comics."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from comicdesk.models import Comic
from comicdesk.services.series_gaps import analyze_series_gaps


@dataclass
class LibraryInsights:
    """Summary counts derived from a library scan."""

    total_files: int = 0
    publishers: dict[str, int] = field(default_factory=dict)
    years: dict[str, int] = field(default_factory=dict)
    series_with_gaps: int = 0
    incomplete_series_names: list[str] = field(default_factory=list)


def compute_library_insights(comics: list[Comic]) -> LibraryInsights:
    """Compute insight metrics without network access."""
    publishers: Counter[str] = Counter()
    years: Counter[str] = Counter()
    for comic in comics:
        publisher = (comic.publisher or "").strip() or "Unknown"
        publishers[publisher] += 1
        year = str(comic.year or comic.volume or "").strip() or "Unknown"
        years[year] += 1

    gap_reports = analyze_series_gaps(comics)
    incomplete = [report.key.label() for report in gap_reports if report.has_gaps]

    return LibraryInsights(
        total_files=len(comics),
        publishers=dict(publishers.most_common(50)),
        years=dict(years.most_common(50)),
        series_with_gaps=len(incomplete),
        incomplete_series_names=incomplete[:100],
    )
