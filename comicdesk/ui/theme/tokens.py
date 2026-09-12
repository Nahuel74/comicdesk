"""Design tokens for ComicDesk."""

THEMES = {
    "dark": {
        "canvas": "#18181b",
        "surface": "#232326",
        "surface_alt": "#2a2a2e",
        "border": "#3f3f46",
        "border_strong": "#52525b",
        "text": "#f4f4f5",
        "text_secondary": "#d4d4d8",
        "muted": "#a1a1aa",
        "accent": "#3b82f6",
        "accent_hover": "#60a5fa",
        "accent_pressed": "#2563eb",
        "selection": "#1e3a5f",
        "hover": "#323238",
        "input_bg": "#2f2f35",
        "changed_field": "#1e3a5f",
        "disabled_bg": "#3f3f46",
        "disabled_text": "#71717a",
        "syntax_tag": "#7dd3fc",
        "syntax_attr": "#bae6fd",
        "syntax_quote": "#fdba74",
        "gridline": "#2f2f35",
        "nav_bg": "#1f1f23",
    },
    "light": {
        "canvas": "#f4f4f5",
        "surface": "#ffffff",
        "surface_alt": "#fafafa",
        "border": "#e4e4e7",
        "border_strong": "#d4d4d8",
        "text": "#18181b",
        "text_secondary": "#3f3f46",
        "muted": "#71717a",
        "accent": "#2563eb",
        "accent_hover": "#3b82f6",
        "accent_pressed": "#1d4ed8",
        "selection": "#dbeafe",
        "hover": "#f4f4f5",
        "input_bg": "#ffffff",
        "changed_field": "#dbeafe",
        "disabled_bg": "#e4e4e7",
        "disabled_text": "#a1a1aa",
        "syntax_tag": "#1d4ed8",
        "syntax_attr": "#1e40af",
        "syntax_quote": "#c2410c",
        "gridline": "#e4e4e7",
        "nav_bg": "#ffffff",
    },
}

VALID_THEMES = frozenset(THEMES)

COLORS = THEMES["dark"]

SPACING = {"xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 24}
FONT_FAMILY = "Inter, Segoe UI, sans-serif"

NAV_COMPACT_WIDTH = 720
ACTION_BAR_COMPACT_WIDTH = 960


def colors_for(theme: str) -> dict:
    """Return color tokens for *theme*, falling back to dark."""
    return THEMES.get(theme, THEMES["dark"])
