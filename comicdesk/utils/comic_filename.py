"""Safe CBZ filename stems that keep human-readable spacing."""

import re

from comicdesk.ui.reading_list_filename import _WINDOWS_RESERVED_FILENAME

_INVALID_FILENAME_CHARS = re.compile(r'[<>:"|?*\\/\x00-\x1f]')


def safe_comic_stem(name: str) -> str:
    """Sanitize a rendered template stem while preserving spaces and punctuation."""
    value = (name or "").strip()
    value = _INVALID_FILENAME_CHARS.sub("", value)
    value = re.sub(r" +", " ", value)
    value = value.strip(" .")
    if not value:
        return ""
    if _WINDOWS_RESERVED_FILENAME.match(value):
        value = f"_{value}"
    return value
