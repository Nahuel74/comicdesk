"""Transform Comic Vine DTOs into editable ComicInfo fields."""

from __future__ import annotations

import html
import re

from comicdesk.models import Comic, ComicVineIssue, ComicVineVolume


def reference_names(values) -> list[str]:
    """Extract stable, non-empty names from Comic Vine relationship objects."""
    result = []
    for value in values or []:
        name = value.get("name", "") if isinstance(value, dict) else str(value or "")
        name = str(name).strip()
        if name and name not in result:
            result.append(name)
    return result


def credits_by_role(credits) -> dict[str, list[str]]:
    """Group people by their Comic Vine role while accepting API variants."""
    roles = {"writer": [], "penciller": [], "inker": [], "colorist": [],
             "letterer": [], "cover_artist": [], "editor": [], "translator": []}
    aliases = {
        "writer": "writer", "writers": "writer", "penciller": "penciller",
        "penciler": "penciller", "inker": "inker", "colorist": "colorist",
        "letterer": "letterer", "cover artist": "cover_artist",
        "cover_artist": "cover_artist", "editor": "editor", "translator": "translator",
    }
    for credit in credits or []:
        if not isinstance(credit, dict):
            continue
        name = str(credit.get("name") or credit.get("person", {}).get("name", "")).strip()
        role = str(credit.get("role") or credit.get("credit") or "").casefold().strip()
        target = aliases.get(role)
        if name and target and name not in roles[target]:
            roles[target].append(name)
    return roles


def apply_issue_metadata(comic: Comic, issue: ComicVineIssue, *, overwrite=False) -> None:
    """Apply rich issue metadata without overwriting manual fields by default."""
    from comicdesk.services.identification import apply_issue_to_comic

    apply_issue_to_comic(comic, issue, overwrite=overwrite)
    values = {
        "summary": _strip_html(issue.description),
        "publisher": issue.publisher,
        "genre": ", ".join(issue.genres),
        "characters": ", ".join(issue.character_credits),
        "locations": ", ".join(issue.location_credits),
        "teams": ", ".join(issue.team_credits),
        "story_arc": ", ".join(issue.story_arc_credits),
        "age_rating": issue.age_rating,
    }
    values.update({field: ", ".join(names) for field, names in credits_by_role(issue.person_credits).items()})
    _fill_fields(comic, values, overwrite)
    if issue.concept_credits:
        _set_field(comic, "tags", ", ".join(issue.concept_credits), overwrite)
    if issue.volume_count_of_issues:
        _set_field(comic, "count", issue.volume_count_of_issues, overwrite)


def apply_volume_metadata(comic: Comic, volume: ComicVineVolume, *, overwrite=False) -> None:
    """Apply series metadata; ComicInfo Volume is the series start year."""
    from comicdesk.services.identification import apply_volume_to_comic

    apply_volume_to_comic(comic, volume, overwrite=overwrite)
    if volume.count_of_issues:
        _set_field(comic, "count", volume.count_of_issues, overwrite)
    _fill_fields(comic, {
        "publisher": volume.publisher,
        "genre": ", ".join(volume.genres),
        "characters": ", ".join(volume.character_credits),
        "locations": ", ".join(volume.location_credits),
        "teams": ", ".join(volume.team_credits),
        "age_rating": volume.age_rating,
    }, overwrite)
    _fill_fields(comic, {field: ", ".join(names)
                         for field, names in credits_by_role(volume.person_credits).items()}, overwrite)


def _fill_fields(comic, values, overwrite):
    for field, value in values.items():
        if value:
            _set_field(comic, field, value, overwrite)


def _set_field(comic, field, value, overwrite):
    if overwrite or not getattr(comic, field, ""):
        setattr(comic, field, value)


def _strip_html(text: str) -> str:
    """Remove HTML tags and decode entities from Comic Vine descriptions."""
    if not text:
        return ""
    cleaned = re.sub(r"<[^>]+>", " ", text)
    cleaned = html.unescape(cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()
