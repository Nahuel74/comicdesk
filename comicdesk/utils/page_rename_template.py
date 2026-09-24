"""Template-based archive page member rename planning."""

from __future__ import annotations

import re
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from pathlib import PurePosixPath

from comicdesk.models import Comic
from comicdesk.services.comic_pages import list_image_pages
from comicdesk.services.comic_archive import read_comic_metadata_fresh
from comicdesk.utils.comic_filename import safe_comic_stem
from comicdesk.utils.rename_template import (
    RenameRowStatus,
    _PLACEHOLDER,
    _PLACEHOLDER_REGISTRY,
    _field_value,
    _parse_placeholder_spec,
    format_issue_number,
    issue_pad_width_for_comic,
    normalize_rendered_stem,
)

DEFAULT_PAGE_TEMPLATE = "{Series} - {Number} - {Page}"

PAGE_QUICK_PLACEHOLDERS: tuple[tuple[str, str], ...] = (
    ("Page", "{Page}"),
    ("Page total", "{PageTotal}"),
    ("Page folder", "{PageFolder}"),
    ("Archive stem", "{ArchiveStem}"),
    ("Series", "{Series}"),
    ("Issue", "{Number}"),
    ("Year", "{Year}"),
    ("Title", "{Title}"),
)


def page_placeholder_help_lines() -> list[str]:
    return [
        "Rename image members inside each archive using {FieldName} placeholders. "
        f"Example: {DEFAULT_PAGE_TEMPLATE}.",
        "{Page} is the 1-based index in archive image order; use “Page digits” for "
        "leading zeros (0 = none). {PageTotal} is the image count.",
        "Issue numbers ({Number}) follow the same rules as Library file rename.",
        "Series and other comic placeholders use the Metadata tab draft when that "
        "issue is open there; otherwise values come from ComicInfo.xml in the archive. "
        "{Series} is the ComicInfo series title (e.g. “Avengers”), not scan release "
        "folder names—use {PageFolder} for that.",
        "{PageFolder} is the parent folder of the image inside the archive "
        "(e.g. a release group directory). {ArchiveStem} is the .cbz/.cbr filename "
        "without extension.",
        "Renamed pages are always written at the archive root; nested folders and "
        "other files inside them are removed.",
    ]


@dataclass(frozen=True)
class RenamePageMemberRow:
    comic: Comic
    old_name: str
    proposed_name: str | None
    status: RenameRowStatus
    message: str = ""


def comic_metadata_for_page_template(
    comic: Comic,
    *,
    metadata_override: Comic | None = None,
) -> Comic:
    """Comic fields for rename templates (Metadata draft, else fresh ComicInfo.xml)."""
    if metadata_override is not None:
        snap = deepcopy(metadata_override)
        snap.path = comic.path
        return snap
    try:
        return read_comic_metadata_fresh(comic.path)
    except Exception:
        return Comic(path=comic.path)


def render_page_member_stem(
    template: str,
    comic: Comic,
    page_index: int,
    page_total: int,
    *,
    old_member_name: str = "",
    issue_pad_width: int = 0,
    page_pad_width: int = 0,
) -> str:
    """Render template to a stem for one archive page (before extension)."""
    default_issue_pad = issue_pad_width_for_comic(comic, issue_pad_width)
    member_posix = PurePosixPath((old_member_name or "").replace("\\", "/"))

    def replace(match: re.Match[str]) -> str:
        spec = match.group(1)
        name, pad = _parse_placeholder_spec(spec, default_issue_pad)
        name_key = name.strip().casefold()
        if name_key == "page":
            if pad > 0:
                return str(page_index).zfill(pad)
            if page_pad_width > 0:
                return str(page_index).zfill(page_pad_width)
            return str(page_index)
        if name_key == "pagetotal":
            return str(page_total)
        if name_key == "pagefolder":
            if len(member_posix.parts) > 1:
                return str(member_posix.parent)
            return ""
        if name_key == "archivestem":
            return comic.path.stem if comic.path else ""
        field = _PLACEHOLDER_REGISTRY.get(name_key)
        if field is None or not hasattr(comic, field):
            return ""
        raw = _field_value(comic, field)
        if field == "issue_number":
            return format_issue_number(raw, pad)
        return raw

    return normalize_rendered_stem(_PLACEHOLDER.sub(replace, template or ""))


def proposed_member_name(
    template: str,
    comic: Comic,
    old_member_name: str,
    page_index: int,
    page_total: int,
    *,
    issue_pad_width: int = 0,
    page_pad_width: int = 0,
) -> str | None:
    """Return full archive member path for *old_member_name*, or None if invalid."""
    stem = render_page_member_stem(
        template,
        comic,
        page_index,
        page_total,
        old_member_name=old_member_name,
        issue_pad_width=issue_pad_width,
        page_pad_width=page_pad_width,
    )
    if not stem.strip():
        return None
    safe_stem = safe_comic_stem(stem)
    if not safe_stem:
        return None
    old_posix = PurePosixPath(old_member_name.replace("\\", "/"))
    ext = old_posix.suffix
    return f"{safe_stem}{ext}"


def plan_page_member_renames(
    comics: list[Comic],
    template: str,
    *,
    issue_pad_width: int = 0,
    page_pad_width: int = 0,
    metadata_for: Callable[[Comic], Comic | None] | None = None,
) -> list[RenamePageMemberRow]:
    """Build preview rows for renaming all image members in each comic."""
    rows: list[RenamePageMemberRow] = []
    for comic in comics:
        if not comic.has_local_file:
            continue
        try:
            page_names = list_image_pages(comic.path)
        except Exception as exc:
            rows.append(
                RenamePageMemberRow(
                    comic=comic,
                    old_name="",
                    proposed_name=None,
                    status=RenameRowStatus.INVALID,
                    message=f"{comic.path.name}: {exc}",
                )
            )
            continue
        if not page_names:
            continue
        override = metadata_for(comic) if metadata_for is not None else None
        template_comic = comic_metadata_for_page_template(
            comic, metadata_override=override
        )
        total = len(page_names)
        draft: list[tuple[str, str | None, str]] = []
        for index, old_name in enumerate(page_names, start=1):
            proposed = proposed_member_name(
                template,
                template_comic,
                old_name,
                index,
                total,
                issue_pad_width=issue_pad_width,
                page_pad_width=page_pad_width,
            )
            if proposed is None:
                draft.append((old_name, None, "invalid"))
            elif proposed == old_name:
                draft.append((old_name, proposed, "unchanged"))
            else:
                draft.append((old_name, proposed, "pending"))

        proposed_targets: dict[str, list[str]] = {}
        for old_name, proposed, state in draft:
            if state != "pending" or proposed is None:
                continue
            proposed_targets.setdefault(proposed, []).append(old_name)
        duplicate_targets = {
            name for name, owners in proposed_targets.items() if len(owners) > 1
        }

        for old_name, proposed, state in draft:
            if state == "invalid":
                rows.append(
                    RenamePageMemberRow(
                        comic=comic,
                        old_name=old_name,
                        proposed_name=None,
                        status=RenameRowStatus.INVALID,
                        message="Invalid or empty filename",
                    )
                )
                continue
            if state == "unchanged":
                rows.append(
                    RenamePageMemberRow(
                        comic=comic,
                        old_name=old_name,
                        proposed_name=proposed,
                        status=RenameRowStatus.UNCHANGED,
                        message="Already matches template",
                    )
                )
                continue
            assert proposed is not None
            status = RenameRowStatus.OK
            message = ""
            if proposed in duplicate_targets:
                status = RenameRowStatus.COLLISION
                message = "Duplicate proposed name in this archive"
            rows.append(
                RenamePageMemberRow(
                    comic=comic,
                    old_name=old_name,
                    proposed_name=proposed,
                    status=status,
                    message=message,
                )
            )
    return rows


def plan_page_rename_apply_allowed(rows: list[RenamePageMemberRow]) -> bool:
    """True when Apply should be enabled."""
    if not rows:
        return False
    return all(
        row.status in (RenameRowStatus.OK, RenameRowStatus.UNCHANGED)
        for row in rows
    )


def rows_for_comic(rows: list[RenamePageMemberRow], comic: Comic) -> list[RenamePageMemberRow]:
    return [row for row in rows if row.comic is comic]


def rename_map_for_comic(rows: list[RenamePageMemberRow], comic: Comic) -> dict[str, str]:
    """Old→new member names for one comic (OK rows only)."""
    mapping: dict[str, str] = {}
    for row in rows:
        if row.comic is not comic or row.status != RenameRowStatus.OK:
            continue
        if row.proposed_name is None:
            continue
        mapping[row.old_name] = row.proposed_name
    return mapping
