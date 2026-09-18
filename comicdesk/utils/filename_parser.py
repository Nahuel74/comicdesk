"""Infer comic metadata from a CBZ filename stem."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


_YEAR = re.compile(r"\((?P<year>19\d{2}|20\d{2})\)")
_VOLUME = re.compile(
    r"(?:^|[\s._-])(?:v|vol(?:ume)?\.?)\s*(?P<volume>\d+)\b",
    re.IGNORECASE,
)
_ISSUE = re.compile(
    r"(?:^|[\s._#-])(?:#\s*)?(?P<issue>\d+(?:\.\d+)?)\s*$",
)
_TRAILING_TAGS = re.compile(r"(\s*[\[{][^\]}]*[\]}])+\s*$")
_TRAILING_PAREN_TAG = re.compile(r"\s*\((?![0-9]{4}\))[^)]*\)\s*$")
_SEPARATORS = re.compile(r"[._]+")


@dataclass(frozen=True)
class ParsedFilename:
    """Metadata inferred from a comic archive filename."""

    series_name: str = ""
    issue_number: str = ""
    volume: str = ""
    year: str = ""


def parse_comic_filename(path: Path | str) -> ParsedFilename:
    """Parse series, issue, volume and year from a file path or stem."""
    if not path:
        return ParsedFilename()
    stem = Path(path).stem.strip()
    if not stem:
        return ParsedFilename()

    stem = _SEPARATORS.sub(" ", stem)
    stem = _TRAILING_TAGS.sub("", stem).strip()
    stem = _strip_trailing_paren_tags(stem)

    year = ""
    year_match = list(_YEAR.finditer(stem))
    if year_match:
        year = year_match[-1].group("year")
        stem = (stem[: year_match[-1].start()] + stem[year_match[-1].end() :]).strip()
        stem = _strip_trailing_paren_tags(stem)

    volume = ""
    volume_match = _VOLUME.search(stem)
    if volume_match:
        volume = _strip_leading_zeros(volume_match.group("volume"))
        stem = (stem[: volume_match.start()] + stem[volume_match.end() :]).strip()

    issue_number = ""
    issue_match = _ISSUE.search(stem)
    if issue_match:
        issue_number = _strip_leading_zeros(issue_match.group("issue"))
        stem = stem[: issue_match.start()].strip()

    series_name = re.sub(r"[\s._-]+", " ", stem).strip(" -_.")
    return ParsedFilename(
        series_name=series_name,
        issue_number=issue_number,
        volume=volume,
        year=year,
    )


def _strip_trailing_paren_tags(stem: str) -> str:
    """Remove trailing release-group parentheticals like (Digital) or (ScanGroup)."""
    while stem:
        match = _TRAILING_PAREN_TAG.search(stem)
        if not match:
            break
        stem = stem[: match.start()].strip()
    return stem


def _strip_leading_zeros(value: str) -> str:
    if "." in value:
        whole, frac = value.split(".", 1)
        return f"{int(whole)}.{frac}" if whole else value
    return str(int(value)) if value.isdigit() else value
