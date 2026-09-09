"""Filename helpers for reading-list file dialogs."""

import re


_WINDOWS_RESERVED_FILENAME = re.compile(
    r"^(?:con|prn|aux|nul|clock\$|com[1-9]|lpt[1-9])(?:\..*)?$",
    re.IGNORECASE,
)


def safe_filename(name):
    """Turn a user-facing list name into a safe, portable filename stem."""
    value = (name or "").strip()
    # Separators must be handled explicitly so a list name can never create
    # another path component when it is used as the dialog's default name.
    value = re.sub(r"[\\/]", "_", value)
    stem = re.sub(r"[^\w.-]+", "_", value, flags=re.UNICODE)
    stem = re.sub(r"_+", "_", stem).strip("._")
    if not stem:
        return "reading_list"

    # Windows reserves these device names even when an extension follows
    # them (the export code appends .cbl to this stem).
    if _WINDOWS_RESERVED_FILENAME.match(stem):
        stem = f"_{stem}"
    return stem
