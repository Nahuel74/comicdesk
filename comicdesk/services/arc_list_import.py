"""Build reading-list entries from Comic Vine story arc issues."""

from __future__ import annotations

import re
from dataclasses import dataclass

from comicdesk.models import Comic, CBLBook, ComicVineIssue


@dataclass(frozen=True)
class ArcReadingListItem:
    """One issue in arc order for library matching."""

    position: int
    series_name: str
    issue_number: str
    cv_issue_id: str
    cv_series_id: str


def normalize_cv_issue_id(value: str) -> str:
    text = str(value or "").strip()
    lower = text.casefold()
    if lower.startswith("4000-"):
        return text[5:].strip()
    return text


def cv_issue_id_for_cbl(value: str) -> str:
    """Stable Comic Vine issue id for CBL references (4000- prefix when numeric)."""
    text = normalize_cv_issue_id(value)
    if not text:
        return ""
    if text.isdigit():
        return f"4000-{text}"
    return text


def _series_issue_from_site_url(site_detail_url: str) -> tuple[str, str]:
    match = re.search(r"comicvine\.gamespot\.com/([^/]+)/4000-", site_detail_url or "", re.I)
    if not match:
        return "", ""
    slug = match.group(1)
    parts = slug.split("-")
    for index in range(len(parts) - 1, 0, -1):
        token = parts[index]
        if re.fullmatch(r"\d+(?:\.\d+)?", token):
            series_slug = "-".join(parts[:index])
            series_name = series_slug.replace("-", " ").strip()
            if series_name:
                series_name = series_name.title()
            return series_name, token
    return "", ""


def arc_items_from_story_arc_stubs(
    stubs: list[dict],
    *,
    arc_title: str = "",
) -> list[ArcReadingListItem]:
    """Build list items from story_arc.issues payload (single API response)."""
    series_hint = ""
    quoted = re.match(r'^"([^"]+)"', (arc_title or "").strip())
    if quoted:
        series_hint = quoted.group(1).strip()
    items: list[ArcReadingListItem] = []
    for position, stub in enumerate(stubs, start=1):
        if not isinstance(stub, dict):
            continue
        raw_id = stub.get("id")
        if raw_id is None or raw_id == "":
            continue
        cv_issue = cv_issue_id_for_cbl(str(raw_id))
        site_url = str(stub.get("site_detail_url") or "")
        series_name, issue_number = _series_issue_from_site_url(site_url)
        if not series_name and series_hint:
            series_name = series_hint
        items.append(
            ArcReadingListItem(
                position=position,
                series_name=series_name,
                issue_number=issue_number,
                cv_issue_id=cv_issue,
                cv_series_id="",
            )
        )
    return items


def arc_items_from_cv_issues(issues: list[ComicVineIssue]) -> list[ArcReadingListItem]:
    items: list[ArcReadingListItem] = []
    for index, issue in enumerate(issues, start=1):
        items.append(
            ArcReadingListItem(
                position=index,
                series_name=issue.series_name,
                issue_number=issue.issue_number,
                cv_issue_id=cv_issue_id_for_cbl(str(issue.id or "")),
                cv_series_id=str(issue.series_id or ""),
            )
        )
    return items


def match_arc_items_to_library(
    items: list[ArcReadingListItem],
    comics: list[Comic],
) -> tuple[list[Comic | CBLBook], int, int]:
    """Return ordered list mixing local comics and fileless CBL books."""
    by_cv_issue: dict[str, Comic] = {}
    by_series_issue: dict[tuple[str, str], Comic] = {}
    for comic in comics:
        issue_id = normalize_cv_issue_id(str(comic.cv_issue_id or ""))
        if issue_id:
            by_cv_issue[issue_id] = comic
        series = (comic.series_name or "").strip().casefold()
        number = (comic.issue_number or "").strip().casefold()
        if series and number:
            by_series_issue[(series, number)] = comic

    ordered: list[Comic | CBLBook] = []
    linked = 0
    missing = 0
    for item in items:
        comic = None
        cv_issue = normalize_cv_issue_id(str(item.cv_issue_id or ""))
        if cv_issue and cv_issue in by_cv_issue:
            comic = by_cv_issue[cv_issue]
        if comic is None:
            key = (
                item.series_name.strip().casefold(),
                item.issue_number.strip().casefold(),
            )
            comic = by_series_issue.get(key)
        if comic is not None:
            ordered.append(comic)
            linked += 1
        else:
            ordered.append(
                CBLBook(
                    series_name=item.series_name,
                    volume="",
                    issue_number=item.issue_number,
                    year="",
                    cv_series_id=item.cv_series_id or None,
                    cv_issue_id=item.cv_issue_id or None,
                    position=item.position,
                )
            )
            missing += 1
    return ordered, linked, missing
