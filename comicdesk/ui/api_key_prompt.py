"""User prompts when Comic Vine API access is required."""

from PySide6.QtWidgets import QMessageBox, QWidget

from comicdesk.config import Config


def has_api_key(config: Config | None) -> bool:
    if config is None:
        return False
    return bool(str(getattr(config, "api_key", "") or "").strip())


def warn_missing_api_key(parent: QWidget | None, action: str = "This action") -> None:
    """Show a modal alert when a Comic Vine API key is missing."""
    QMessageBox.warning(
        parent,
        "Comic Vine API key required",
        (
            f"{action} requires a Comic Vine API key.\n\n"
            "Open Settings (Ctrl+,) and add your API key under Comic Vine."
        ),
    )


def ensure_api_key(parent: QWidget | None, config: Config | None, action: str = "This action") -> bool:
    """Return True when an API key is configured; otherwise warn the user."""
    if has_api_key(config):
        return True
    warn_missing_api_key(parent, action)
    return False
