"""Normalize Comic Vine Web links stored in ComicInfo."""

from __future__ import annotations

from comicdesk.utils.url_parser import extract_comicvine_ids


def link_covers_issue_id(url: str, issue_id: str) -> bool:
    """Return True when a URL refers to the given Comic Vine issue id."""
    parsed = extract_comicvine_ids(str(url or ""))
    return parsed.get("issue_id") == str(issue_id or "").strip()


def _issue_url_rank(url: str) -> int:
    """Prefer human-readable slug URLs over generic /issue/ paths."""
    lowered = str(url or "").casefold()
    if "/issue/4000-" in lowered:
        return 0
    return 1


def normalize_issue_web_links(
    links,
    *,
    issue_id: str,
    preferred_url: str = "",
) -> list[str]:
    """Keep non-CV links and a single canonical issue URL; drop volume links."""
    issue_id = str(issue_id or "").strip()
    kept_other: list[str] = []
    issue_candidates: list[str] = []

    preferred = str(preferred_url or "").strip()
    if preferred and link_covers_issue_id(preferred, issue_id):
        issue_candidates.append(preferred)

    for raw in links or []:
        link = str(raw or "").strip()
        if not link or link in issue_candidates:
            continue
        parsed = extract_comicvine_ids(link)
        if parsed.get("series_id") and not parsed.get("issue_id"):
            continue
        if parsed.get("issue_id"):
            if issue_id and parsed["issue_id"] == issue_id:
                issue_candidates.append(link)
            continue
        if "comicvine.gamespot.com" in link.casefold():
            continue
        if link not in kept_other:
            kept_other.append(link)

    result = list(kept_other)
    if issue_id and issue_candidates:
        best = max(issue_candidates, key=_issue_url_rank)
        result.append(best)
    return result
