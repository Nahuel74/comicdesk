"""Detect missing issue numbers per series from a scanned library."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

from comicdesk.models import Comic, CBLBook


@dataclass(frozen=True)
class SeriesGroupKey:
    """Stable grouping key for a comic series in the library."""

    cv_series_id: str
    series_name: str
    volume_year: str

    def label(self) -> str:
        name = self.series_name or "Unknown series"
        if self.volume_year:
            return f"{name} ({self.volume_year})"
        return name


@dataclass
class SeriesGapReport:
    """Missing issue numbers for one series group."""

    key: SeriesGroupKey
    expected_count: int
    present_numbers: list[float] = field(default_factory=list)
    missing_numbers: list[float] = field(default_factory=list)
    comics: list[Comic] = field(default_factory=list)

    @property
    def is_complete(self) -> bool:
        return not self.missing_numbers and self.expected_count > 0

    @property
    def has_gaps(self) -> bool:
        return bool(self.missing_numbers)


def _group_key(comic: Comic) -> SeriesGroupKey:
    series_id = str(comic.cv_series_id or "").strip()
    series_name = (comic.series_name or "").strip()
    volume_year = str(comic.volume or "").strip()
    if series_id:
        return SeriesGroupKey(series_id, series_name, volume_year)
    return SeriesGroupKey("", series_name, volume_year)


def _parse_issue_number(value: str) -> float | None:
    text = (value or "").strip()
    if not text:
        return None
    match = re.match(r"^(\d+(?:\.\d+)?)", text.replace(",", "."))
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _expected_count(comics: Iterable[Comic]) -> int:
    for comic in comics:
        raw = str(comic.count or "").strip()
        if raw.isdigit():
            count = int(raw)
            if count > 0:
                return count
    return 0


def analyze_series_gaps(comics: Iterable[Comic]) -> list[SeriesGapReport]:
    """Group comics and list missing integer issue numbers up to Count."""
    groups: dict[SeriesGroupKey, list[Comic]] = {}
    for comic in comics:
        key = _group_key(comic)
        if not key.cv_series_id and not key.series_name:
            continue
        groups.setdefault(key, []).append(comic)

    reports: list[SeriesGapReport] = []
    for key, members in sorted(groups.items(), key=lambda item: item[0].label().casefold()):
        present: set[float] = set()
        for comic in members:
            parsed = _parse_issue_number(comic.issue_number or "")
            if parsed is not None:
                present.add(parsed)
        expected = _expected_count(members)
        missing: list[float] = []
        if expected > 0:
            for number in range(1, expected + 1):
                if float(number) not in present:
                    missing.append(float(number))
        reports.append(
            SeriesGapReport(
                key=key,
                expected_count=expected,
                present_numbers=sorted(present),
                missing_numbers=missing,
                comics=list(members),
            )
        )
    return reports


def all_missing_issues_as_cbl_books(
    reports: Iterable[SeriesGapReport],
) -> list[CBLBook]:
    """Wishlist CBL references for every missing issue across gap reports."""
    books: list[CBLBook] = []
    for report in reports:
        if not report.has_gaps:
            continue
        books.extend(missing_issues_as_cbl_books(report))
    return books


def missing_issues_as_cbl_books(report: SeriesGapReport) -> list[CBLBook]:
    """Build wishlist-ready CBL references for missing issue numbers."""
    books: list[CBLBook] = []
    sample = report.comics[0] if report.comics else None
    series_name = report.key.series_name or (sample.series_name if sample else "")
    volume = report.key.volume_year or (str(sample.volume or "") if sample else "")
    cv_series = report.key.cv_series_id or (str(sample.cv_series_id or "") if sample else None)
    for position, number in enumerate(report.missing_numbers, start=1):
        issue_label = str(int(number)) if number == int(number) else str(number)
        books.append(
            CBLBook(
                series_name=series_name,
                volume=volume,
                issue_number=issue_label,
                year=volume,
                cv_series_id=cv_series or None,
                position=position,
            )
        )
    return books
