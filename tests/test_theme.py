"""Tests for theme tokens and stylesheet builders."""

from comicdesk.config import normalize_theme
from comicdesk.ui.theme import (
    application_stylesheet,
    colors_for,
    dialog_stylesheet,
    resolve_effective_theme,
    syntax_colors,
    table_stylesheet,
)


def test_colors_for_dark_and_light_differ():
    dark = colors_for("dark")
    light = colors_for("light")
    assert dark["canvas"] != light["canvas"]
    assert dark["text"] != light["text"]
    assert dark["accent"] != light["accent"]


def test_colors_for_unknown_theme_falls_back_to_dark():
    assert colors_for("neon") == colors_for("dark")


def test_normalize_theme_accepts_only_known_values():
    assert normalize_theme("light") == "light"
    assert normalize_theme("dark") == "dark"
    assert normalize_theme("system") == "system"
    assert normalize_theme("invalid") == "dark"
    assert normalize_theme("") == "dark"


def test_application_stylesheet_includes_key_selectors():
    qss = application_stylesheet("dark")
    assert "QTabWidget::pane" in qss
    assert "QPushButton" in qss
    assert "QComboBox" in qss
    assert "QTableView" in qss
    assert "QCheckBox::indicator" in qss


def test_light_stylesheet_uses_light_canvas_color():
    qss = application_stylesheet("light")
    assert colors_for("light")["canvas"] in qss


def test_table_and_dialog_stylesheets_are_non_empty():
    assert table_stylesheet("dark")
    assert dialog_stylesheet("light")


def test_table_stylesheet_sets_alternate_row_color_from_tokens():
    qss = table_stylesheet("light")
    assert "alternate-background-color" in qss
    assert colors_for("light")["row_alt"] in qss


def test_resolve_effective_theme_for_explicit_preferences():
    assert resolve_effective_theme("dark") == "dark"
    assert resolve_effective_theme("light") == "light"


def test_syntax_colors_follow_theme():
    dark = syntax_colors("dark")
    light = syntax_colors("light")
    assert dark["tag"] != light["tag"]
