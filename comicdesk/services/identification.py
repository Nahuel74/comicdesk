"""Match a local comic to Comic Vine issues or volumes."""

from __future__ import annotations

import re
import html
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from comicdesk.models import Comic, ComicVineIssue, ComicVineVolume
from comicdesk.services.comicvine_api import SEARCH_RESULT_LIMIT
from comicdesk.utils.comicvine_web_links import normalize_issue_web_links
from comicdesk.utils.filename_parser import parse_comic_filename

STATUS_EXACT = "exact"
STATUS_CANDIDATES = "candidates"
STATUS_EMPTY = "empty"

_MAX_VOLUME_ISSUE_LOOKUPS = 3


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


def identify_comic(comic: Comic, client, *, issues_only: bool = False) -> IdentificationResult:
    """Identify a comic without mutating it or auto-picking ambiguous hits."""
    parsed = parse_comic_filename(comic.path)
    hint_year = _publication_year_hint(comic, parsed)

    if comic.cv_issue_id:
        issue = client.get_issue(comic.cv_issue_id)
        return IdentificationResult(STATUS_EXACT, issue=issue, issues=[issue])

    issue_number = _issue_number_for_lookup(comic, parsed)
    series_name = (comic.series_name or "").strip() or parsed.series_name
    if comic.cv_series_id and issue_number:
        listed = _list_issues_on_volume(client, comic.cv_series_id, issue_number)
        exact = _unique_issue_match(listed, series_name, issue_number)
        if exact:
            _enrich_issue_volume_from_comic(comic, exact)
            hydrated = _hydrate_exact_issue(client, exact)
            if hydrated is not None:
                exact = hydrated
            return IdentificationResult(STATUS_EXACT, issue=exact, issues=[exact])
        if listed:
            narrowed = _narrow_issues_by_year(listed, hint_year)
            if len(narrowed) == 1:
                issue = narrowed[0]
                _enrich_issue_volume_from_comic(comic, issue)
                hydrated = _hydrate_exact_issue(client, issue)
                if hydrated is not None:
                    issue = hydrated
                return IdentificationResult(STATUS_EXACT, issue=issue, issues=[issue])
            if narrowed:
                return IdentificationResult(STATUS_CANDIDATES, issues=narrowed)
            return IdentificationResult(STATUS_CANDIDATES, issues=listed)
        return IdentificationResult(STATUS_EMPTY)

    if series_name and issue_number:
        by_volume = _lookup_by_volume_and_issue(
            client, series_name, issue_number, hint_year
        )
        if by_volume.status != STATUS_EMPTY:
            return by_volume

    title = (comic.title or "").strip()
    queries = []
    if series_name and issue_number:
        queries.append((f"{series_name} #{issue_number}", series_name, issue_number))
        queries.append((f"{series_name} {issue_number}", series_name, issue_number))
        if not (series_name or "").strip().casefold().startswith(("the ", "a ", "an ")):
            prefixed = f"The {series_name.strip()} {issue_number}"
            queries.append((prefixed, series_name, issue_number))
    if series_name and title and not issue_number:
        queries.append((f"{series_name} {title}", series_name, ""))

    inferred_series = series_name
    inferred_issue = issue_number
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
        result = _from_issue_search(searched, query_series, query_issue, hint_year)
        if result.status == STATUS_EXACT and result.issue is not None:
            hydrated = _hydrate_exact_issue(client, result.issue)
            if hydrated is not None:
                result = IdentificationResult(
                    STATUS_EXACT, issue=hydrated, issues=[hydrated]
                )
        if result.status != STATUS_EMPTY:
            return result

    if inferred_series and not issues_only:
        volumes = client.search_volume(inferred_series)
        if volumes and hint_year:
            by_year = [
                volume
                for volume in volumes
                if _volume_matches_year_hint(_volume_start_year(volume), hint_year)
            ]
            if by_year:
                volumes = by_year
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
    cover_date = (issue.store_date or issue.cover_date or "").split("-")
    for field_name, value in zip(("year", "month", "day"), cover_date):
        if value and (overwrite or not getattr(comic, field_name)):
            setattr(comic, field_name, value)
    if issue.web_url and issue.web_url not in comic.web_links:
        comic.web_links.append(issue.web_url)
    _apply_issue_rich_fields(comic, issue, overwrite)
    resolved_issue_id = str(issue.id or comic.cv_issue_id or "").strip()
    if resolved_issue_id:
        comic.web_links = normalize_issue_web_links(
            comic.web_links,
            issue_id=resolved_issue_id,
            preferred_url=issue.web_url or "",
        )


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
    if volume.web_url and not comic.cv_issue_id and volume.web_url not in comic.web_links:
        comic.web_links.append(volume.web_url)
    _apply_volume_rich_fields(comic, volume, overwrite)


def _apply_issue_rich_fields(comic, issue, overwrite):
    values = {
        "summary": _strip_html(issue.description), "publisher": issue.publisher,
        "imprint": getattr(issue, "imprint", ""),
        "genre": ", ".join(issue.genres), "characters": ", ".join(issue.character_credits),
        "locations": ", ".join(issue.location_credits), "teams": ", ".join(issue.team_credits),
        "story_arc": ", ".join(issue.story_arc_credits), "age_rating": issue.age_rating,
    }
    from comicdesk.services.comicvine_mapping import credits_by_role
    values.update({k: ", ".join(v) for k, v in credits_by_role(issue.person_credits).items()})
    from comicdesk.services.comicinfo import COMMA_SEPARATED_FIELDS, format_comma_separated

    for field, value in values.items():
        if not value:
            continue
        if field in COMMA_SEPARATED_FIELDS:
            value = format_comma_separated(value)
        if overwrite or not getattr(comic, field, ""):
            setattr(comic, field, value)
    if issue.concept_credits and (overwrite or not comic.tags):
        comic.tags = format_comma_separated(", ".join(issue.concept_credits))
    if issue.volume_count_of_issues and (overwrite or not comic.count):
        comic.count = issue.volume_count_of_issues
    deck = (getattr(issue, "deck", "") or "").strip()
    if deck and (overwrite or not (comic.notes or "").strip()):
        comic.notes = deck


def _apply_volume_rich_fields(comic, volume, overwrite):
    from comicdesk.services.comicvine_mapping import credits_by_role
    values = {"publisher": volume.publisher, "genre": ", ".join(volume.genres),
              "characters": ", ".join(volume.character_credits),
              "locations": ", ".join(volume.location_credits),
              "teams": ", ".join(volume.team_credits), "age_rating": volume.age_rating}
    from comicdesk.services.comicinfo import COMMA_SEPARATED_FIELDS, format_comma_separated

    values.update({k: ", ".join(v) for k, v in credits_by_role(volume.person_credits).items()})
    for field, value in values.items():
        if not value:
            continue
        if field in COMMA_SEPARATED_FIELDS:
            value = format_comma_separated(value)
        if overwrite or not getattr(comic, field, ""):
            setattr(comic, field, value)
    if volume.count_of_issues and (overwrite or not comic.count):
        comic.count = volume.count_of_issues


def _from_issue_search(
    results: list[ComicVineIssue],
    series_name: str,
    issue_number: str,
    hint_year: str = "",
) -> IdentificationResult:
    matches = [issue for issue in results if _series_matches(issue.series_name, series_name)]
    if issue_number:
        matches = [issue for issue in matches if _issue_matches(issue.issue_number, issue_number)]
    if len(matches) > 1 and hint_year:
        narrowed = _narrow_issues_by_year(matches, hint_year)
        if narrowed:
            matches = narrowed
    if len(matches) == 1:
        issue = matches[0]
        return IdentificationResult(STATUS_EXACT, issue=issue, issues=[issue])
    if matches:
        return IdentificationResult(STATUS_CANDIDATES, issues=matches)
    if results and not issue_number:
        return IdentificationResult(STATUS_CANDIDATES, issues=results)
    return IdentificationResult(STATUS_EMPTY)


def _series_name_search_variants(series_name: str) -> list[str]:
    name = (series_name or "").strip()
    if not name:
        return []
    variants = [name]
    parts = name.split()
    if len(parts) >= 3 and parts[1].casefold() == "x":
        hyphenated = f"{parts[0]} X-{' '.join(parts[2:])}"
        if hyphenated not in variants:
            variants.append(hyphenated)
    return variants


def _volume_search_queries(series_name: str, hint_year: str = "") -> list[str]:
    queries: list[str] = []
    for name in _series_name_search_variants(series_name):
        queries.append(name)
        lowered = name.casefold()
        if not lowered.startswith(("the ", "a ", "an ")):
            queries.append(f"The {name}")
        if hint_year:
            queries.append(f"{name} {hint_year}")
            try:
                queries.append(f"{name} {int(hint_year) - 1}")
            except ValueError:
                pass
    seen: set[str] = set()
    ordered: list[str] = []
    for query in queries:
        if query in seen:
            continue
        seen.add(query)
        ordered.append(query)
    return ordered


def _volume_filter_years(hint_year: str) -> list[str]:
    years = []
    if hint_year:
        years.append(hint_year)
        try:
            years.append(str(int(hint_year) - 1))
        except ValueError:
            pass
    return years


def _exact_series_volume_names(series_name: str) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for name in _series_name_search_variants(series_name):
        candidates = [name]
        if not name.casefold().startswith(("the ", "a ", "an ")):
            candidates.append(f"The {name}")
        for candidate in candidates:
            key = candidate.strip().casefold()
            if key and key not in seen:
                seen.add(key)
                names.append(candidate)
    return names


def _is_main_series_volume(volume_name: str, series_name: str) -> bool:
    return _series_matches(volume_name, series_name)


def _volume_lookup_rank(volume, hint_year: str) -> tuple[int, str]:
    start = _volume_start_year(volume)
    if hint_year and _volume_matches_year_hint(start, hint_year):
        return (0, start)
    if hint_year and start:
        try:
            gap = int(hint_year) - int(start)
            if 0 <= gap <= 25:
                return (1, start)
        except ValueError:
            pass
    return (2, start)


def _collect_volume_candidates(client, series_name: str, hint_year: str = "") -> list:
    seen_ids: set[str] = set()
    candidates: list = []

    def add(volume) -> None:
        volume_id = str(getattr(volume, "id", "") or "")
        if not volume_id or volume_id in seen_ids:
            return
        if not _is_main_series_volume(volume.name, series_name):
            return
        seen_ids.add(volume_id)
        candidates.append(volume)

    filter_fn = getattr(client, "filter_volumes", None)
    if callable(filter_fn):
        for volume_name in _exact_series_volume_names(series_name):
            try:
                for volume in filter_fn(name=volume_name):
                    add(volume)
            except Exception:
                continue

    for query in _volume_search_queries(series_name, hint_year):
        try:
            for volume in client.search_volume(query):
                add(volume)
        except Exception:
            continue

    candidates.sort(key=lambda volume: _volume_lookup_rank(volume, hint_year))
    return candidates[:_MAX_VOLUME_ISSUE_LOOKUPS]


def _search_matched_volumes(client, series_name: str, hint_year: str = "") -> list:
    return _collect_volume_candidates(client, series_name, hint_year)


def _series_issue_search_queries(series_name: str, issue_number: str) -> list[str]:
    queries: list[str] = []
    seen: set[str] = set()
    for name in _series_name_search_variants(series_name):
        for candidate in (f"{name} {issue_number}", f"{name} #{issue_number}"):
            if not name.casefold().startswith(("the ", "a ", "an ")):
                candidate_the = f"The {name} {issue_number}"
                if candidate_the not in seen:
                    seen.add(candidate_the)
                    queries.append(candidate_the)
            if candidate not in seen:
                seen.add(candidate)
                queries.append(candidate)
    return queries


def _lookup_by_issue_number_filter(
    client, series_name: str, issue_number: str, hint_year: str = ""
) -> IdentificationResult:
    matches: list[ComicVineIssue] = []
    search_issue = getattr(client, "search_issue", None)
    if callable(search_issue):
        for query in _series_issue_search_queries(series_name, issue_number):
            try:
                listed = search_issue(query)
            except Exception:
                continue
            for item in listed:
                if not _series_matches(item.series_name, series_name):
                    continue
                if not _issue_matches(item.issue_number, issue_number):
                    continue
                matches.append(item)
            if matches:
                break

    search = getattr(client, "search_issues_by_number", None)
    if not matches and callable(search):
        try:
            listed = search(issue_number)
        except Exception:
            listed = []
        matches = [
            item
            for item in listed
            if _series_matches(item.series_name, series_name)
            and _issue_matches(item.issue_number, issue_number)
        ]
    if not matches:
        return IdentificationResult(STATUS_EMPTY)
    if len(matches) > 1 and hint_year:
        narrowed = _narrow_issues_by_year(matches, hint_year)
        if len(narrowed) == 1:
            exact = _hydrate_exact_issue(client, narrowed[0]) or narrowed[0]
            return IdentificationResult(STATUS_EXACT, issue=exact, issues=[exact])
        if narrowed:
            matches = narrowed
    if len(matches) == 1:
        exact = _hydrate_exact_issue(client, matches[0]) or matches[0]
        return IdentificationResult(STATUS_EXACT, issue=exact, issues=[matches])
    return IdentificationResult(STATUS_CANDIDATES, issues=matches)


def _issues_from_matched_volumes(
    client,
    matched_volumes: list,
    series_name: str,
    issue_number: str,
    hint_year: str,
) -> IdentificationResult:
    issues: list[ComicVineIssue] = []
    seen_ids: set[str] = set()
    for volume in matched_volumes[:_MAX_VOLUME_ISSUE_LOOKUPS]:
        try:
            listed = _list_issues_on_volume(client, volume.id, issue_number)
        except Exception:
            continue
        volume_issues: list[ComicVineIssue] = []
        for candidate in listed:
            if not _issue_matches(candidate.issue_number, issue_number):
                continue
            if not _series_matches(candidate.series_name, series_name):
                continue
            if candidate.id in seen_ids:
                continue
            seen_ids.add(candidate.id)
            hydrated = _hydrate_exact_issue(client, candidate) or candidate
            volume_issues.append(hydrated)
        if not volume_issues:
            continue
        issues.extend(volume_issues)
        if len(volume_issues) == 1:
            issue = volume_issues[0]
            if not hint_year or _issue_matches_year_hint(issue, hint_year):
                return IdentificationResult(STATUS_EXACT, issue=issue, issues=[issue])
        break
    if len(issues) > 1 and hint_year:
        narrowed = _narrow_issues_by_year(issues, hint_year)
        if len(narrowed) == 1:
            return IdentificationResult(STATUS_EXACT, issue=narrowed[0], issues=narrowed)
        if narrowed:
            issues = narrowed
    if len(issues) == 1:
        return IdentificationResult(STATUS_EXACT, issue=issues[0], issues=issues)
    if issues:
        return IdentificationResult(STATUS_CANDIDATES, issues=issues)
    return IdentificationResult(STATUS_EMPTY)


def _lookup_by_volume_and_issue(
    client, series_name: str, issue_number: str, hint_year: str = ""
) -> IdentificationResult:
    """Resolve an issue by series name and number via volume search + issue filter."""
    matched_volumes = _search_matched_volumes(client, series_name, hint_year)
    if matched_volumes:
        by_volume = _issues_from_matched_volumes(
            client, matched_volumes, series_name, issue_number, hint_year
        )
        if by_volume.status != STATUS_EMPTY:
            return by_volume

    return _lookup_by_issue_number_filter(
        client, series_name, issue_number, hint_year
    )


def _list_issues_on_volume(client, volume_id: str, issue_number: str) -> list[ComicVineIssue]:
    """List issues on a volume; retry without issue_number filter when the API returns none."""
    listed = client.list_issues(volume_id, issue_number)
    if listed or not (issue_number or "").strip():
        return listed
    try:
        on_volume = client.list_issues(volume_id, None)
    except Exception:
        return []
    volume_key = str(volume_id).strip()
    return [
        item
        for item in on_volume
        if str(item.series_id or "").strip() == volume_key
        and _issue_matches(item.issue_number, issue_number)
    ]


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


_ISSUE_OF_COUNT_SUFFIX = re.compile(r"\s*\(of\s+\d+\)\s*$", re.IGNORECASE)
_LEADING_ARTICLE = re.compile(r"^(?:the|a|an)\s+")


def _issue_number_for_lookup(comic: Comic, parsed) -> str:
    """Resolve an issue number for Comic Vine lookup.

    ComicInfo often stores pack positions like ``03 (of 05)`` while filenames
    parse to a plain issue number; prefer the filename when the suffix is present.
    """
    local = (comic.issue_number or "").strip()
    from_name = (parsed.issue_number or "").strip()
    if local and _ISSUE_OF_COUNT_SUFFIX.search(local) and from_name:
        return from_name
    if local:
        stripped = _ISSUE_OF_COUNT_SUFFIX.sub("", local).strip().lstrip("#")
        if stripped:
            return stripped
    return from_name


def _norm_series_key(value: str) -> str:
    text = _norm_series(value)
    return _LEADING_ARTICLE.sub("", text).strip()


def _series_matches(left: str, right: str) -> bool:
    return _norm_series_key(left) == _norm_series_key(right)


def _issue_matches(left: str, right: str) -> bool:
    return _norm_issue(left) == _norm_issue(right)


def _norm_series(value: str) -> str:
    """Normalize series names for punctuation-insensitive equality."""
    text = (value or "").strip().casefold()
    text = re.sub(r"[^\w\s]+", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def _norm_text(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().casefold())


_DIR_YEAR = re.compile(r"\((?P<year>19\d{2}|20\d{2})\)")


def _year_from_directory_name(name: str) -> str:
    matches = list(_DIR_YEAR.finditer(name or ""))
    if not matches:
        return ""
    return matches[-1].group("year")


def _publication_year_hint(comic: Comic, parsed) -> str:
    for candidate in (comic.year, parsed.year):
        text = (candidate or "").strip()
        if re.fullmatch(r"(19|20)\d{2}", text):
            return text
    volume = (comic.volume or "").strip()
    if re.fullmatch(r"(19|20)\d{2}", volume):
        return volume
    raw_path = getattr(comic, "path", None)
    if raw_path:
        path = Path(raw_path) if not isinstance(raw_path, Path) else raw_path
        for directory in (path.parent, path.parent.parent):
            if directory == directory.parent:
                continue
            year = _year_from_directory_name(directory.name)
            if year:
                return year
    return ""


def _volume_start_year(volume: ComicVineVolume) -> str:
    return (getattr(volume, "start_year", None) or "").strip()


def _issue_publication_year(issue: ComicVineIssue) -> str:
    for value in (
        (issue.store_date or "").split("-")[0],
        (issue.cover_date or "").split("-")[0],
        issue.volume_start_year,
    ):
        text = (value or "").strip()
        if re.fullmatch(r"(19|20)\d{2}", text):
            return text
    volume = (issue.volume or "").strip()
    if re.fullmatch(r"(19|20)\d{2}", volume):
        return volume
    return ""


def _volume_matches_year_hint(start_year: str, hint_year: str) -> bool:
    """Match filename/ComicInfo year to a volume's start_year.

    Cover/store years in filenames are often one calendar year after the
    parent volume's Comic Vine start_year (e.g. Excalibur 2004 series, #8 in 2005).
    """
    start = (start_year or "").strip()
    hint = (hint_year or "").strip()
    if not hint:
        return True
    if not start:
        return False
    if start == hint:
        return True
    try:
        return int(hint) - int(start) == 1
    except ValueError:
        return False


def _issue_matches_year_hint(issue: ComicVineIssue, hint_year: str) -> bool:
    if not hint_year:
        return True
    publication = _issue_publication_year(issue)
    if publication:
        return publication == hint_year
    return _volume_matches_year_hint(issue.volume_start_year, hint_year)


def _narrow_issues_by_year(
    issues: list[ComicVineIssue], hint_year: str
) -> list[ComicVineIssue]:
    if not hint_year:
        return list(issues)
    return [
        issue for issue in issues if _issue_matches_year_hint(issue, hint_year)
    ]


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


def _hydrate_exact_issue(client, issue: ComicVineIssue):
    """Fetch complete issue details by ID for a search result.

    Search results from the Comic Vine API return partial payloads without
    credits, descriptions or accurate volume metadata.  This helper replaces
    the partial object with a fully hydrated one when possible.
    """
    if not getattr(issue, "id", None):
        return None
    if issue_needs_hydrate(issue):
        try:
            return client.get_issue(issue.id)
        except Exception:
            return None
    if issue_needs_volume_resolve(issue):
        try:
            client.resolve_parent_volume(issue)
        except Exception:
            return None
    return issue


def issue_needs_volume_resolve(issue: ComicVineIssue) -> bool:
    """Return True when parent volume data may still fill issue fields."""
    from comicdesk.services.comicvine_api import issue_needs_parent_volume_lookup

    return issue_needs_parent_volume_lookup(issue)


def issue_needs_hydrate(issue: ComicVineIssue) -> bool:
    """Return True when a search/list hit still needs a get_issue round trip."""
    if not getattr(issue, "id", None):
        return False
    credits = getattr(issue, "person_credits", None)
    return not credits


def _enrich_issue_volume_from_comic(comic: Comic, issue: ComicVineIssue) -> None:
    """Use local series/year metadata to avoid an extra volume API lookup."""
    series_id = (comic.cv_series_id or "").strip()
    if not series_id or str(issue.series_id or "").strip() != series_id:
        return
    year = (comic.volume or "").strip()
    if not re.fullmatch(r"(19|20)\d{2}", year):
        return
    if not (issue.volume_start_year or "").strip():
        issue.volume_start_year = year
    if not re.fullmatch(r"(19|20)\d{2}", (issue.volume or "").strip()):
        issue.volume = year


def _strip_html(text: str) -> str:
    """Remove HTML tags and decode entities from Comic Vine descriptions."""
    if not text:
        return ""
    cleaned = re.sub(r"<[^>]+>", " ", text)
    cleaned = html.unescape(cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()
