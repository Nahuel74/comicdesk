"""Transactional editing session for one comic's metadata."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import fields
from typing import Any
import xml.etree.ElementTree as ET

from comicdesk.models import Comic
from comicdesk.services.comicinfo import FIELD_TAGS, split_web_links
from comicdesk.models import ComicVineVolume
from comicdesk.services.identification import apply_issue_to_comic, apply_volume_to_comic


EDITABLE_FIELDS = tuple(field_name for _, field_name in FIELD_TAGS)
IDENTIFIER_FIELDS = ("cv_series_id", "cv_issue_id")


class MetadataSession:
    """Keep a mutable draft separate from the comic shown by the application.

    A session is intentionally small and UI agnostic.  The original object is
    changed only by :meth:`commit`, which should be called after persistence
    succeeds.
    """

    def __init__(self, comic: Comic):
        if comic is None:
            raise ValueError("a comic is required")
        self.original = comic
        self.draft = deepcopy(comic)
        self._saved_draft = deepcopy(comic)

    @property
    def comic(self) -> Comic:
        """Compatibility alias for the object being edited."""
        return self.original

    @property
    def is_dirty(self) -> bool:
        return not _same_comic(self.draft, self._saved_draft)

    @property
    def dirty(self) -> bool:
        return self.is_dirty

    def snapshot(self) -> Comic:
        """Return an isolated copy suitable for a background worker."""
        return deepcopy(self.draft)

    def set_field(self, field_name: str, value: Any) -> None:
        """Set one supported ComicInfo or Comic Vine identifier field."""
        if field_name not in EDITABLE_FIELDS + IDENTIFIER_FIELDS:
            raise AttributeError(f"unsupported metadata field: {field_name}")
        if field_name == "web_links":
            if isinstance(value, str):
                value = split_web_links(value)
            else:
                value = list(value or [])
        elif value is None:
            value = ""
        else:
            value = str(value)
        setattr(self.draft, field_name, value)

    set_value = set_field

    def apply_proposal(self, issue: Any, *, overwrite: bool = False) -> None:
        """Apply an explicitly selected issue or volume to the draft only."""
        if issue is None:
            raise ValueError("a metadata proposal is required")
        if isinstance(issue, ComicVineVolume):
            apply_volume_to_comic(self.draft, issue, overwrite=overwrite)
        else:
            apply_issue_to_comic(self.draft, issue, overwrite=overwrite)

    apply_issue = apply_proposal

    def discard(self) -> None:
        """Restore the last committed values without touching the original."""
        self.draft = deepcopy(self._saved_draft)

    def commit(self) -> Comic:
        """Copy the draft into the original after a successful disk write."""
        for field in fields(self.original):
            setattr(self.original, field.name, deepcopy(getattr(self.draft, field.name)))
        self._saved_draft = deepcopy(self.original)
        self.draft = deepcopy(self.original)
        return self.original

    @property
    def original_comic(self) -> Comic:
        return self.original

    @property
    def draft_comic(self) -> Comic:
        return self.draft

    def mark_saved(self) -> Comic:
        """Explicit name for the post-write commit operation."""
        return self.commit()

    def values(self) -> dict[str, Any]:
        """Return editable values for form population."""
        names = EDITABLE_FIELDS + IDENTIFIER_FIELDS
        return {name: deepcopy(getattr(self.draft, name, "")) for name in names}

    apply_candidate = apply_proposal


def _same_comic(left: Comic, right: Comic) -> bool:
    """Compare snapshots while treating copied XML elements by content."""
    for field in fields(left):
        if not _same_value(getattr(left, field.name), getattr(right, field.name)):
            return False
    return True


def _same_value(left: Any, right: Any) -> bool:
    if isinstance(left, ET.Element) or isinstance(right, ET.Element):
        if not isinstance(left, ET.Element) or not isinstance(right, ET.Element):
            return False
        return ET.tostring(left) == ET.tostring(right)
    if isinstance(left, (list, tuple)) or isinstance(right, (list, tuple)):
        if not isinstance(left, (list, tuple)) or not isinstance(right, (list, tuple)):
            return False
        return len(left) == len(right) and all(_same_value(a, b) for a, b in zip(left, right))
    return left == right


MetadataEditSession = MetadataSession
