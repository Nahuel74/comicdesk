"""Template-based CBZ filename planning from Comic metadata."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from comicdesk.models import Comic
from comicdesk.services.comicinfo import FIELD_TAGS
from comicdesk.utils.comic_filename import safe_comic_stem

_PLACEHOLDER = re.compile(r"\{([^{}]+)\}")


class RenameRowStatus(StrEnum):
    OK = "ok"
    UNCHANGED = "unchanged"
    EXCLUDED = "excluded"
    INVALID = "invalid"
    COLLISION = "collision"


@dataclass(frozen=True)
class RenamePlanRow:
    comic: Comic
    old_path: Path
    proposed_path: Path | None
    status: RenameRowStatus
    message: str = ""


def _build_placeholder_registry() -> dict[str, str]:
    """Map case-insensitive placeholder names to Comic attribute names."""
    registry: dict[str, str] = {}
    for xml_tag, field_name in FIELD_TAGS:
        registry[xml_tag.casefold()] = field_name
        registry[field_name.casefold()] = field_name
    return registry


_PLACEHOLDER_REGISTRY = _build_placeholder_registry()

# (button label, token inserted into the template field)
QUICK_PLACEHOLDERS: tuple[tuple[str, str], ...] = (
    ("Series", "{Series}"),
    ("Issue", "{Number}"),
    ("Year", "{Year}"),
    ("Title", "{Title}"),
    ("Volume", "{Volume}"),
    ("Publisher", "{Publisher}"),
    ("Writer", "{Writer}"),
    ("Month", "{Month}"),
    ("Count", "{Count}"),
    ("Imprint", "{Imprint}"),
    ("Story arc", "{StoryArc}"),
)


def placeholder_help_lines() -> list[str]:
    """Short help lines for UI."""
    return [
        "Type a filename pattern using {FieldName} placeholders (see buttons below). "
        "Example: {Series} - {Number} ({Year}).",
        "Issue numbers ({Number}): when ComicInfo Count is set, leading zeros match the "
        "series length (Count 9 → 2 digits, 99 → 3, 999 → 4). Without Count, use "
        "“Fallback issue digits” (0 = no zeros). Force a width with {Number:3}.",
        "{Volume} is ComicInfo “Volume” (often the series start/publication year). "
        "{Year} is the issue’s Year field.",
    ]


def count_derived_issue_pad_width(comic: Comic) -> int | None:
    """Return zero-pad width from ComicInfo Count, or None when Count is missing/invalid."""
    raw = _field_value(comic, "count").strip()
    if not raw:
        return None
    try:
        total = int(float(raw))
    except ValueError:
        return None
    if total <= 0:
        return None
    return len(str(total)) + 1


def issue_pad_width_for_comic(comic: Comic, manual_width: int) -> int:
    """Pad width for {Number} when the template does not specify :digits."""
    derived = count_derived_issue_pad_width(comic)
    if derived is not None:
        return derived
    return max(0, manual_width)


def format_issue_number(raw: str, pad_width: int) -> str:
    """Pad the leading integer in an issue string with zeros (*pad_width* > 0)."""
    if pad_width <= 0 or not raw:
        return raw or ""
    text = raw.strip()
    match = re.match(r"^(\d+)(.*)$", text)
    if not match:
        return text
    return match.group(1).zfill(pad_width) + match.group(2)


def _parse_placeholder_spec(spec: str, default_pad_width: int) -> tuple[str, int]:
    name, _, width_text = spec.strip().partition(":")
    if width_text.isdigit():
        return name, int(width_text)
    return name, default_pad_width


def _field_value(comic: Comic, field_name: str) -> str:
    value = getattr(comic, field_name, "")
    if field_name == "web_links":
        if isinstance(value, (list, tuple, set)):
            return ", ".join(str(item) for item in value if str(item).strip())
        return str(value or "")
    if isinstance(value, (list, tuple, set)):
        return ", ".join(str(item) for item in value)
    return str(value or "")


def placeholder_values(comic: Comic, *, issue_pad_width: int = 0) -> dict[str, str]:
    """All supported placeholder names (lowercase keys) and rendered values."""
    pad = issue_pad_width_for_comic(comic, issue_pad_width)
    values: dict[str, str] = {}
    for xml_tag, field_name in FIELD_TAGS:
        raw = _field_value(comic, field_name)
        if field_name == "issue_number":
            raw = format_issue_number(raw, pad)
        values[xml_tag.casefold()] = raw
        values[field_name.casefold()] = raw
    return values


def _substitute_placeholders(
    template: str, comic: Comic, *, issue_pad_width: int = 0
) -> str:
    default_pad = issue_pad_width_for_comic(comic, issue_pad_width)

    def replace(match: re.Match[str]) -> str:
        spec = match.group(1)
        name, pad = _parse_placeholder_spec(spec, default_pad)
        name_key = name.strip().casefold()
        field = _PLACEHOLDER_REGISTRY.get(name_key)
        if field is None or not hasattr(comic, field):
            return ""
        raw = _field_value(comic, field)
        if field == "issue_number":
            return format_issue_number(raw, pad)
        return raw

    return _PLACEHOLDER.sub(replace, template or "")


def normalize_rendered_stem(text: str) -> str:
    """Collapse whitespace and strip empty placeholder artifacts from a rendered stem."""
    value = re.sub(r"\s+", " ", (text or "").strip())
    value = re.sub(r"\(\s*\)", "", value)
    value = re.sub(r"\[\s*\]", "", value)
    value = re.sub(r"\{\s*\}", "", value)
    # Trim separator runs left when adjacent fields were empty.
    value = re.sub(r"\s*-\s*-\s*", " - ", value)
    value = re.sub(r"(?<=\S)\s*-\s*(?=\)|$)", "", value)
    value = re.sub(r"^\s*-\s*|\s*-\s*$", "", value)
    value = re.sub(r"\(\s+", "(", value)
    value = re.sub(r"\s+\)", ")", value)
    value = re.sub(r"\s+", " ", value).strip(" -_.")
    return value


def render_template(
    template: str, comic: Comic, *, issue_pad_width: int = 0
) -> str:
    """Render a user template to a raw stem string (before filename sanitization)."""
    return normalize_rendered_stem(
        _substitute_placeholders(template, comic, issue_pad_width=issue_pad_width)
    )


def rendered_stem_to_filename(stem: str) -> str:
    """Sanitize a rendered stem for use as a CBZ filename (without extension)."""
    return safe_comic_stem(stem)


def proposed_path_for_comic(
    template: str, comic: Comic, *, issue_pad_width: int = 0
) -> Path | None:
    """Return the proposed .cbz path for *comic*, or None if invalid."""
    if not comic.has_local_file:
        return None
    raw = render_template(template, comic, issue_pad_width=issue_pad_width)
    if not raw.strip():
        return None
    stem = rendered_stem_to_filename(raw)
    if not stem:
        return None
    return comic.path.parent / f"{stem}.cbz"


def plan_renames(
    comics: list[Comic], template: str, *, issue_pad_width: int = 0
) -> list[RenamePlanRow]:
    """Build preview rows with validation for a batch rename."""
    rows: list[RenamePlanRow] = []
    local: list[Comic] = []
    for comic in comics:
        if not comic.has_local_file:
            rows.append(
                RenamePlanRow(
                    comic=comic,
                    old_path=comic.path,
                    proposed_path=None,
                    status=RenameRowStatus.EXCLUDED,
                    message="No local CBZ file",
                )
            )
            continue
        local.append(comic)

    sources = {c.path.resolve() for c in local}
    draft: list[tuple[Comic, Path, Path | None, str]] = []

    for comic in local:
        old_path = comic.path
        proposed = proposed_path_for_comic(
            template, comic, issue_pad_width=issue_pad_width
        )
        if proposed is None:
            draft.append((comic, old_path, None, "Invalid or empty filename"))
            continue
        if proposed.resolve() == old_path.resolve():
            draft.append((comic, old_path, proposed, "unchanged"))
            continue
        draft.append((comic, old_path, proposed, "pending"))

    proposed_targets: dict[Path, list[Comic]] = {}
    for comic, _old, proposed, state in draft:
        if state != "pending" or proposed is None:
            continue
        key = proposed.resolve()
        proposed_targets.setdefault(key, []).append(comic)

    duplicate_targets = {path for path, owners in proposed_targets.items() if len(owners) > 1}

    old_to_proposed: dict[Path, Path | None] = {}
    for comic, old_path, proposed, state in draft:
        if state == "unchanged":
            old_to_proposed[old_path.resolve()] = old_path.resolve()
        elif state == "pending" and proposed is not None:
            old_to_proposed[old_path.resolve()] = proposed.resolve()

    for comic, old_path, proposed, state in draft:
        if state == "Invalid or empty filename":
            rows.append(
                RenamePlanRow(
                    comic=comic,
                    old_path=old_path,
                    proposed_path=None,
                    status=RenameRowStatus.INVALID,
                    message="Invalid or empty filename",
                )
            )
            continue
        if state == "unchanged":
            rows.append(
                RenamePlanRow(
                    comic=comic,
                    old_path=old_path,
                    proposed_path=proposed,
                    status=RenameRowStatus.UNCHANGED,
                    message="Already matches template",
                )
            )
            continue

        assert proposed is not None
        target = proposed.resolve()
        message = ""
        status = RenameRowStatus.OK

        if target in duplicate_targets:
            status = RenameRowStatus.COLLISION
            message = "Duplicate proposed filename in this batch"
        elif target.exists() and target != old_path.resolve():
            if target not in sources:
                status = RenameRowStatus.COLLISION
                message = "A file with this name already exists"
            else:
                occupant = next(c for c in local if c.path.resolve() == target)
                occupant_target = old_to_proposed.get(occupant.path.resolve())
                if occupant_target == target:
                    status = RenameRowStatus.COLLISION
                    message = "Target name is already used by another comic in this batch"

        rows.append(
            RenamePlanRow(
                comic=comic,
                old_path=old_path,
                proposed_path=proposed,
                status=status,
                message=message,
            )
        )

    return rows


def plan_apply_allowed(rows: list[RenamePlanRow]) -> bool:
    """True when Apply should be enabled (no blocking invalid/collision/excluded-only batch)."""
    actionable = [row for row in rows if row.status != RenameRowStatus.EXCLUDED]
    if not actionable:
        return False
    return all(
        row.status in (RenameRowStatus.OK, RenameRowStatus.UNCHANGED)
        for row in actionable
    )
