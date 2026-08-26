"""Shared visual tokens and application-level Qt styles."""

from PySide6.QtGui import QFont


COLORS = {
    "canvas": "#1e1e1e",
    "surface": "#252526",
    "surface_alt": "#2b2b2b",
    "border": "#3d3d3d",
    "border_strong": "#4d4d4d",
    "text": "#e0e0e0",
    "muted": "#808080",
    "accent": "#0e639c",
    "accent_hover": "#1177bb",
    "accent_pressed": "#094771",
    "selection": "#264f78",
    "hover": "#2d2d2d",
}

SPACING = {"xs": 4, "sm": 8, "md": 12, "lg": 16}
FONT_FAMILY = "Inter, Segoe UI, sans-serif"


def application_font() -> QFont:
    """Return the default font used by the workspace."""
    font = QFont(FONT_FAMILY.split(",")[0], 10)
    font.setStyleHint(QFont.SansSerif)
    return font


def application_stylesheet() -> str:
    """Build the common application stylesheet from the visual tokens."""
    c = COLORS
    return f"""
        QMainWindow, QWidget#workspace {{
            background-color: {c['canvas']};
            color: {c['text']};
        }}
        QMenuBar, QMenu, QStatusBar {{
            background-color: {c['surface_alt']};
            color: {c['text']};
        }}
        QMenuBar {{ border-bottom: 1px solid {c['border']}; }}
        QMenuBar::item:selected, QMenu::item:selected {{
            background-color: {c['selection']};
        }}
        QMenu {{ border: 1px solid {c['border']}; }}
        QStatusBar {{ border-top: 1px solid {c['border']}; }}
        QSplitter {{ background-color: {c['canvas']}; }}
        QSplitter::handle {{
            background-color: {c['border_strong']};
        }}
        QSplitter::handle:hover {{ background-color: {c['accent']}; }}
        QToolTip {{
            color: {c['text']}; background-color: {c['surface_alt']};
            border: 1px solid {c['border_strong']};
        }}
    """


def workspace_topbar_stylesheet() -> str:
    """Style the compact workspace identity bar."""
    c = COLORS
    return f"""
        QWidget#workspaceTopbar {{
            background-color: {c['surface']};
            border-bottom: 1px solid {c['border']};
        }}
        QLabel#workspaceTitle {{
            color: {c['text']}; font-size: 15px; font-weight: 600;
        }}
        QLabel#workspaceHint {{ color: {c['muted']}; font-size: 11px; }}
    """
