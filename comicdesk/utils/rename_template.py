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


@dataclass(frozen=True)
class RenameFolderPlanRow:
    """One series/volume folder rename affecting one or more local comics."""

    folder_old: Path
    folder_new: Path | None
    comics: tuple[Comic, ...]
    status: RenameRowStatus
    message: str = ""


DEFAULT_FOLDER_TEMPLATE = "{Series} ({Volume})"

# Subfolders under a series directory that get their own folder rename (not rolled up).
_DISTINCT_SERIES_SUBFOLDER_NAMES = frozenset(
    {
        "annual",
        "annuals",
        "special",
        "specials",
        "one-shot",
        "one shot",
        "oneshot",
        "tpb",
        "tpbs",
        "trade",
        "trades",
        "hardcover",
        "hc",
    }
)
_DISTINCT_SERIES_SUBFOLDER_RE = re.compile(
    r"\b(annuals?|one[- ]?shots?|specials?|tpbs?|trades?)\b", re.IGNORECASE
)


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


def placeholder_help_lines(*, for_folders: bool = False) -> list[str]:
    """Short help lines for UI."""
    lines = [
        "Type a filename pattern using {FieldName} placeholders (see buttons below). "
        "Example: {Series} - {Number} ({Year}).",
        "Issue numbers ({Number}): when ComicInfo Count is set, leading zeros match the "
        "series length (Count 9 → 2 digits, 99 → 3, 999 → 4). Without Count, use "
        "“Fallback issue digits” (0 = no zeros). Force a width with {Number:3}.",
        "{Volume} is ComicInfo “Volume” (often the series start/publication year). "
        "{Year} is the issue’s Year field.",
    ]
    if for_folders:
        lines.append(
            "Series folders: every comic in the same series folder must produce the "
            "same name from your template. If preview shows invalid, align metadata on "
            "all issues (Series, Volume, etc.) or drop per-issue fields such as {Number}."
        )
    return lines


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
                    message="No local comic file",
                )
            )
            continue
        if comic.path.suffix.lower() == ".cbr":
            rows.append(
                RenamePlanRow(
                    comic=comic,
                    old_path=comic.path,
                    proposed_path=None,
                    status=RenameRowStatus.EXCLUDED,
                    message="Save metadata first to convert the archive, then rename",
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


def series_folder_for_comic(comic: Comic, library_root: Path) -> Path | None:
    """Series/volume directory for *comic* relative to the scanned library folder."""
    if not comic.has_local_file:
        return None
    root = Path(library_root).resolve()
    file_parent = comic.path.parent.resolve()
    if file_parent == root:
        return root
    try:
        relative = file_parent.relative_to(root)
    except ValueError:
        return None
    parts = relative.parts
    if not parts:
        return root
    if len(parts) == 1:
        return file_parent
    if _is_distinct_series_subfolder(parts[-1]):
        return file_parent
    return root / parts[0]


def _is_distinct_series_subfolder(name: str) -> bool:
    """True when a nested folder should rename on its own (Annual, Special, etc.)."""
    key = name.strip().casefold()
    if key in _DISTINCT_SERIES_SUBFOLDER_NAMES:
        return True
    return _DISTINCT_SERIES_SUBFOLDER_RE.search(name) is not None


def proposed_series_folder_name(
    template: str, comic: Comic, *, issue_pad_width: int = 0
) -> str:
    """Rendered folder name (sanitized) for *comic*, or empty when invalid."""
    raw = render_template(template, comic, issue_pad_width=issue_pad_width)
    if not raw.strip():
        return ""
    return rendered_stem_to_filename(raw)


def folder_rename_error_message(title: str, detail: str) -> str:
    """Short title on the first line; remaining lines are detail (UI adds an error icon)."""
    title = title.strip()
    detail = (detail or "").strip()
    return f"{title}\n{detail}" if detail else title


def _series_folder_name_mismatch_message(
    members: tuple[Comic, ...], names: set[str]
) -> str:
    """Explain why a shared series folder cannot be renamed with this template."""
    count = len(members)
    distinct = len(names)
    samples = sorted(names, key=str.casefold)[:3]
    lines = [f"· {name}" for name in samples]
    if distinct > len(samples):
        lines.append(f"· … +{distinct - len(samples)} more")
    detail = (
        f"{count} comics · {distinct} different names\n"
        + "\n".join(lines)
        + "\nAlign Series, Volume on every issue."
    )
    return folder_rename_error_message("Names do not match", detail)


def proposed_series_folder_path(
    template: str,
    comic: Comic,
    library_root: Path,
    *,
    issue_pad_width: int = 0,
) -> Path | None:
    """Proposed series folder path for *comic*, or None when invalid."""
    old_folder = series_folder_for_comic(comic, library_root)
    if old_folder is None:
        return None
    name = proposed_series_folder_name(template, comic, issue_pad_width=issue_pad_width)
    if not name:
        return None
    return old_folder.parent / name


def plan_folder_renames(
    comics: list[Comic],
    template: str,
    library_root: Path,
    *,
    issue_pad_width: int = 0,
) -> list[RenameFolderPlanRow]:
    """Build preview rows for batch series-folder renames (one row per distinct folder)."""
    root = Path(library_root).resolve()
    groups: dict[Path, list[Comic]] = {}
    excluded: list[tuple[Comic, str]] = []

    for comic in comics:
        if not comic.has_local_file:
            excluded.append((comic, "No local comic file"))
            continue
        folder = series_folder_for_comic(comic, root)
        if folder is None:
            excluded.append((comic, "Comic is outside the scanned library folder"))
            continue
        groups.setdefault(folder.resolve(), []).append(comic)

    rows: list[RenameFolderPlanRow] = []
    for comic, message in excluded:
        rows.append(
            RenameFolderPlanRow(
                folder_old=comic.path.parent,
                folder_new=None,
                comics=(comic,),
                status=RenameRowStatus.EXCLUDED,
                message=message,
            )
        )

    draft: list[tuple[Path, tuple[Comic, ...], Path | None, str, str]] = []

    for old_folder in sorted(groups.keys(), key=lambda p: str(p).casefold()):
        members = tuple(groups[old_folder])
        names: set[str] = set()
        invalid_message = ""
        for comic in members:
            name = proposed_series_folder_name(
                template, comic, issue_pad_width=issue_pad_width
            )
            if not name:
                invalid_message = folder_rename_error_message(
                    "Empty folder name",
                    "The template produced no name for one or more issues.",
                )
                break
            names.add(name)
        if invalid_message:
            draft.append((old_folder, members, None, "invalid", invalid_message))
            continue
        if len(names) > 1:
            draft.append(
                (
                    old_folder,
                    members,
                    None,
                    "invalid",
                    _series_folder_name_mismatch_message(members, names),
                )
            )
            continue
        proposed = old_folder.parent / names.pop()
        if proposed.resolve() == old_folder:
            draft.append((old_folder, members, proposed, "unchanged", ""))
        else:
            draft.append((old_folder, members, proposed, "pending", ""))

    source_folders = set(groups.keys())

    proposed_targets: dict[Path, list[Path]] = {}
    for old_folder, _members, proposed, state, _msg in draft:
        if state != "pending" or proposed is None:
            continue
        key = proposed.resolve()
        proposed_targets.setdefault(key, []).append(old_folder)

    duplicate_targets = {
        path for path, owners in proposed_targets.items() if len(owners) > 1
    }

    old_to_proposed: dict[Path, Path | None] = {}
    for old_folder, _members, proposed, state, _msg in draft:
        if state == "unchanged":
            old_to_proposed[old_folder] = old_folder
        elif state == "pending" and proposed is not None:
            old_to_proposed[old_folder] = proposed.resolve()

    for old_folder, members, proposed, state, message in draft:
        if state == "invalid":
            rows.append(
                RenameFolderPlanRow(
                    folder_old=old_folder,
                    folder_new=None,
                    comics=members,
                    status=RenameRowStatus.INVALID,
                    message=message,
                )
            )
            continue
        if state == "unchanged":
            rows.append(
                RenameFolderPlanRow(
                    folder_old=old_folder,
                    folder_new=proposed,
                    comics=members,
                    status=RenameRowStatus.UNCHANGED,
                    message="Already matches template",
                )
            )
            continue

        assert proposed is not None
        target = proposed.resolve()
        status = RenameRowStatus.OK
        detail = ""

        if target in duplicate_targets:
            status = RenameRowStatus.COLLISION
            detail = folder_rename_error_message(
                "Name conflict",
                "Duplicate proposed folder name in this batch",
            )
        elif target.exists() and target != old_folder:
            if target not in source_folders:
                status = RenameRowStatus.COLLISION
                detail = folder_rename_error_message(
                    "Name conflict",
                    "A folder with this name already exists",
                )
            else:
                occupant_proposed = old_to_proposed.get(target)
                if occupant_proposed == target:
                    status = RenameRowStatus.COLLISION
                    detail = folder_rename_error_message(
                        "Name conflict",
                        "Another folder in this batch already uses that name",
                    )

        rows.append(
            RenameFolderPlanRow(
                folder_old=old_folder,
                folder_new=proposed,
                comics=members,
                status=status,
                message=detail,
            )
        )

    return rows


def plan_folder_apply_allowed(rows: list[RenameFolderPlanRow]) -> bool:
    """True when folder Apply should be enabled."""
    actionable = [row for row in rows if row.status != RenameRowStatus.EXCLUDED]
    if not actionable:
        return False
    return all(
        row.status in (RenameRowStatus.OK, RenameRowStatus.UNCHANGED)
        for row in actionable
    )
