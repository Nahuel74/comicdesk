"""Match a local comic to Comic Vine issues or volumes."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from cbl_maker.models import Comic, ComicVineIssue, ComicVineVolume
from cbl_maker.utils.filename_parser import parse_comic_filename

STATUS_EXACT = "exact"
STATUS_CANDIDATES = "candidates"
STATUS_EMPTY = "empty"


@dataclass
class IdentificationResult:
    """Outcome of a Comic Vine identification attempt."""

    status: str
    issue: Optional[ComicVineIssue] = None
    issues: list[ComicVineIssue] = field(default_factory=list)
    volumes: list[ComicVineVolume] = field(default_factory=list)

    @property
    def is_exact(self) -> bool:
        return self.status == STATUS_EXACT

    @property
    def candidates(self):
        """Return the candidates exposed by the result's active kind."""
        return self.issues or self.volumes


def identify_comic(comic: Comic, client) -> IdentificationResult:
    """Identify a comic without mutating it or auto-picking ambiguous hits."""
    if comic.cv_issue_id:
        issue = client.get_issue(comic.cv_issue_id)
        return IdentificationResult(STATUS_EXACT, issue=issue, issues=[issue])

    issue_number = (comic.issue_number or "").strip()
    if comic.cv_series_id and issue_number:
        listed = client.list_issues(comic.cv_series_id, issue_number)
        exact = _unique_issue_match(listed, comic.series_name, issue_number)
        if exact:
            return IdentificationResult(STATUS_EXACT, issue=exact, issues=[exact])
        if listed:
            return IdentificationResult(STATUS_CANDIDATES, issues=listed)

    parsed = parse_comic_filename(comic.path)
    series_name = (comic.series_name or "").strip()
    title = (comic.title or "").strip()
    queries = []
    if series_name and issue_number:
        queries.append((f"{series_name} #{issue_number}", series_name, issue_number))
    if series_name and title and not issue_number:
        queries.append((f"{series_name} {title}", series_name, ""))

    inferred_series = series_name or parsed.series_name
    inferred_issue = issue_number or parsed.issue_number
    inferred_title = title
    if inferred_series and inferred_issue:
        query = (f"{inferred_series} #{inferred_issue}", inferred_series, inferred_issue)
        if query[0] not in {item[0] for item in queries}:
            queries.append(query)
    if parsed.series_name and parsed.issue_number:
        query = (
            f"{parsed.series_name} #{parsed.issue_number}",
            parsed.series_name,
            parsed.issue_number,
        )
        if query[0] not in {item[0] for item in queries}:
            queries.append(query)
    elif inferred_series and inferred_title:
        query = (f"{inferred_series} {inferred_title}", inferred_series, "")
        if query[0] not in {item[0] for item in queries}:
            queries.append(query)

    for query, query_series, query_issue in queries:
        try:
            searched = client.search_issue(query)
        except Exception:
            continue
        result = _from_issue_search(searched, query_series, query_issue)
        if result.status != STATUS_EMPTY:
            return result

    if inferred_series:
        volumes = client.search_volume(inferred_series)
        if volumes:
            return IdentificationResult(STATUS_CANDIDATES, volumes=volumes)

    return IdentificationResult(STATUS_EMPTY)


def apply_issue_to_comic(
    comic: Comic, issue: ComicVineIssue, *, overwrite: bool = False
) -> None:
    """Copy selected issue fields, preserving manual values by default."""
    comic.cv_metadata = issue
    if issue.id and (overwrite or not comic.cv_issue_id):
        comic.cv_issue_id = issue.id
    if issue.series_id and (overwrite or not comic.cv_series_id):
        comic.cv_series_id = issue.series_id
    if issue.series_name and (overwrite or not comic.series_name):
        comic.series_name = issue.series_name
    # ComicInfo's Volume field is the publication/start year in this app.
    # Never copy Comic Vine's parent-volume database id into it.
    volume_year = issue.volume_start_year or issue.volume
    # Older imports could have stored the parent volume id here. Replace that
    # known-invalid value even when manual-field preservation is enabled.
    if volume_year and (overwrite or not comic.volume or comic.volume == issue.series_id):
        comic.volume = volume_year
    if issue.issue_number and (overwrite or not comic.issue_number):
        comic.issue_number = issue.issue_number
    if issue.name and (overwrite or not comic.title):
        comic.title = issue.name
    cover_date = (issue.cover_date or "").split("-")
    for field_name, value in zip(("year", "month", "day"), cover_date):
        if value and (overwrite or not getattr(comic, field_name)):
            setattr(comic, field_name, value)
    if issue.web_url and issue.web_url not in comic.web_links:
        comic.web_links.append(issue.web_url)
    _apply_issue_rich_fields(comic, issue, overwrite)


def apply_volume_to_comic(
    comic: Comic, volume: ComicVineVolume, *, overwrite: bool = False
) -> None:
    """Apply series-level data without inventing an issue identifier."""
    if volume.id and (overwrite or not comic.cv_series_id):
        comic.cv_series_id = volume.id
    if volume.name and (overwrite or not comic.series_name):
        comic.series_name = volume.name
    if volume.start_year and (overwrite or not comic.volume or comic.volume == volume.id):
        comic.volume = volume.start_year
    if volume.web_url and volume.web_url not in comic.web_links:
        comic.web_links.append(volume.web_url)
    _apply_volume_rich_fields(comic, volume, overwrite)


def _apply_issue_rich_fields(comic, issue, overwrite):
    values = {
        "summary": issue.description, "publisher": issue.publisher,
        "genre": ", ".join(issue.genres), "characters": ", ".join(issue.character_credits),
        "locations": ", ".join(issue.location_credits), "teams": ", ".join(issue.team_credits),
        "story_arc": ", ".join(issue.story_arc_credits), "age_rating": issue.age_rating,
    }
    from cbl_maker.services.comicvine_mapping import credits_by_role
    values.update({k: ", ".join(v) for k, v in credits_by_role(issue.person_credits).items()})
    for field, value in values.items():
        if value and (overwrite or not getattr(comic, field, "")):
            setattr(comic, field, value)
    if issue.volume_count_of_issues and (overwrite or not comic.count):
        comic.count = issue.volume_count_of_issues


def _apply_volume_rich_fields(comic, volume, overwrite):
    from cbl_maker.services.comicvine_mapping import credits_by_role
    values = {"publisher": volume.publisher, "genre": ", ".join(volume.genres),
              "characters": ", ".join(volume.character_credits),
              "locations": ", ".join(volume.location_credits),
              "teams": ", ".join(volume.team_credits), "age_rating": volume.age_rating}
    values.update({k: ", ".join(v) for k, v in credits_by_role(volume.person_credits).items()})
    for field, value in values.items():
        if value and (overwrite or not getattr(comic, field, "")):
            setattr(comic, field, value)
    if volume.count_of_issues and (overwrite or not comic.count):
        comic.count = volume.count_of_issues


def _from_issue_search(
    results: list[ComicVineIssue], series_name: str, issue_number: str
) -> IdentificationResult:
    matches = [issue for issue in results if _series_matches(issue.series_name, series_name)]
    if issue_number:
        matches = [issue for issue in matches if _issue_matches(issue.issue_number, issue_number)]
    if len(matches) == 1:
        issue = matches[0]
        return IdentificationResult(STATUS_EXACT, issue=issue, issues=[issue])
    if matches:
        return IdentificationResult(STATUS_CANDIDATES, issues=matches)
    if results:
        return IdentificationResult(STATUS_CANDIDATES, issues=results)
    return IdentificationResult(STATUS_EMPTY)


def _unique_issue_match(
    issues: list[ComicVineIssue], series_name: str, issue_number: str
) -> Optional[ComicVineIssue]:
    numbered = [i for i in issues if _issue_matches(i.issue_number, issue_number)]
    if series_name:
        named = [i for i in numbered if _series_matches(i.series_name, series_name)]
        if len(named) == 1:
            return named[0]
        if named:
            return None
    if len(numbered) == 1:
        return numbered[0]
    if len(issues) == 1 and _issue_matches(issues[0].issue_number, issue_number):
        return issues[0]
    return None


def _series_matches(left: str, right: str) -> bool:
    return _norm_text(left) == _norm_text(right)


def _issue_matches(left: str, right: str) -> bool:
    return _norm_issue(left) == _norm_issue(right)


def _norm_text(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().casefold())


def _norm_issue(value: str) -> str:
    text = (value or "").strip().lstrip("#").casefold()
    if not text:
        return ""
    if re.fullmatch(r"\d+", text):
        return str(int(text))
    match = re.fullmatch(r"(\d+)\.(\d+)", text)
    if match:
        whole, frac = match.groups()
        return f"{int(whole)}.{frac}" if int(frac) else str(int(whole))
    return text
