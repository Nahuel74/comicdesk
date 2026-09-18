"""Resolve stored theme preferences to effective light/dark palettes."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication

EFFECTIVE_THEMES = frozenset({"dark", "light"})


def resolve_effective_theme(preference: str, app=None) -> str:
    """Map dark, light, or system to the palette used for QSS and tokens."""
    if preference in EFFECTIVE_THEMES:
        return preference
    if preference != "system":
        return "dark"
    gui_app = app or QGuiApplication.instance()
    if gui_app is None:
        return "dark"
    scheme = gui_app.styleHints().colorScheme()
    if scheme == Qt.ColorScheme.Light:
        return "light"
    if scheme == Qt.ColorScheme.Dark:
        return "dark"
    return "dark"
