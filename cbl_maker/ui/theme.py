"""Shared visual tokens and application-level Qt styles."""

from PySide6.QtGui import QFont

THEMES = {
    "dark": {
        "canvas": "#1e1e1e",
        "surface": "#252526",
        "surface_alt": "#2b2b2b",
        "border": "#3d3d3d",
        "border_strong": "#4d4d4d",
        "text": "#e0e0e0",
        "text_secondary": "#b8b8b8",
        "muted": "#808080",
        "accent": "#0e639c",
        "accent_hover": "#1177bb",
        "accent_pressed": "#094771",
        "selection": "#264f78",
        "hover": "#2d2d2d",
        "input_bg": "#3c3c3c",
        "changed_field": "#1a3a5c",
        "disabled_bg": "#3d3d3d",
        "disabled_text": "#6d6d6d",
        "syntax_tag": "#569cd6",
        "syntax_attr": "#9cdcfe",
        "syntax_quote": "#ce9178",
        "gridline": "#2d2d2d",
    },
    "light": {
        "canvas": "#f3f3f3",
        "surface": "#ffffff",
        "surface_alt": "#f5f5f5",
        "border": "#d4d4d4",
        "border_strong": "#c8c8c8",
        "text": "#1e1e1e",
        "text_secondary": "#424242",
        "muted": "#6e6e6e",
        "accent": "#0066b8",
        "accent_hover": "#0078d4",
        "accent_pressed": "#005a9e",
        "selection": "#add6ff",
        "hover": "#e8e8e8",
        "input_bg": "#ffffff",
        "changed_field": "#cce5ff",
        "disabled_bg": "#e0e0e0",
        "disabled_text": "#9e9e9e",
        "syntax_tag": "#0000ff",
        "syntax_attr": "#001080",
        "syntax_quote": "#a31515",
        "gridline": "#e0e0e0",
    },
}

VALID_THEMES = frozenset(THEMES)

COLORS = THEMES["dark"]

SPACING = {"xs": 4, "sm": 8, "md": 12, "lg": 16}
FONT_FAMILY = "Inter, Segoe UI, sans-serif"


def colors_for(theme: str) -> dict:
    """Return color tokens for *theme*, falling back to dark."""
    return THEMES.get(theme, THEMES["dark"])


def application_font() -> QFont:
    """Return the default font used by the workspace."""
    font = QFont(FONT_FAMILY.split(",")[0], 10)
    font.setStyleHint(QFont.SansSerif)
    return font


def _common_widget_styles(c: dict) -> str:
    """QSS rules shared across application and dialog scopes."""
    return f"""
        QPushButton {{
            background-color: {c['disabled_bg']};
            color: {c['text']};
            border: none;
            padding: 6px 12px;
            border-radius: 4px;
        }}
        QPushButton:hover {{
            background-color: {c['border_strong']};
        }}
        QPushButton:pressed {{
            background-color: {c['border']};
        }}
        QPushButton:disabled {{
            background-color: {c['disabled_bg']};
            color: {c['disabled_text']};
        }}
        QPushButton[primary="true"] {{
            background-color: {c['accent']};
            color: white;
            font-weight: bold;
        }}
        QPushButton[primary="true"]:hover {{
            background-color: {c['accent_hover']};
        }}
        QPushButton[primary="true"]:pressed {{
            background-color: {c['accent_pressed']};
        }}
        QPushButton[primary="true"]:disabled {{
            background-color: {c['disabled_bg']};
            color: {c['disabled_text']};
        }}
        QToolButton {{
            border: none;
            color: {c['text']};
            background: transparent;
        }}
        QToolButton:hover {{
            background-color: {c['border']};
            border-radius: 4px;
        }}
        QLineEdit, QTextEdit, QPlainTextEdit, QComboBox {{
            background-color: {c['input_bg']};
            color: {c['text']};
            border: 1px solid {c['border']};
            border-radius: 4px;
            padding: 4px 8px;
        }}
        QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus {{
            border: 1px solid {c['accent']};
        }}
        QComboBox::drop-down {{
            border: none;
            width: 20px;
        }}
        QComboBox QAbstractItemView {{
            background-color: {c['surface']};
            color: {c['text']};
            border: 1px solid {c['border']};
            selection-background-color: {c['selection']};
        }}
        QTableView, QTableWidget {{
            background-color: {c['canvas']};
            color: {c['text']};
            border: none;
            gridline-color: {c['gridline']};
        }}
        QTableView::item, QTableWidget::item {{
            padding: 6px;
        }}
        QTableView::item:selected, QTableWidget::item:selected {{
            background-color: {c['selection']};
            color: {c['text']};
        }}
        QHeaderView::section {{
            background-color: {c['surface_alt']};
            color: {c['text']};
            padding: 8px;
            border: none;
            border-right: 1px solid {c['border']};
            font-weight: bold;
        }}
        QTreeView {{
            background-color: {c['canvas']};
            color: {c['text']};
            border: none;
            outline: none;
        }}
        QTreeView::item {{
            padding: 6px 4px;
            min-height: 24px;
        }}
        QTreeView::item:selected {{
            background-color: {c['selection']};
        }}
        QTreeView::item:hover:!selected {{
            background-color: {c['hover']};
        }}
        QTreeView::branch {{
            background-color: {c['canvas']};
        }}
        QTreeView::branch:hover {{
            background-color: {c['hover']};
        }}
        QListWidget {{
            background-color: {c['surface']};
            color: {c['text']};
            border: 1px solid {c['border']};
            border-radius: 4px;
        }}
        QListWidget::item:selected {{
            background-color: {c['selection']};
        }}
        QScrollArea {{
            background-color: {c['canvas']};
            border: none;
        }}
        QScrollArea > QWidget > QWidget {{
            background-color: {c['canvas']};
        }}
        QScrollBar:vertical {{
            background: {c['surface']};
            width: 12px;
            border: none;
        }}
        QScrollBar::handle:vertical {{
            background: {c['border_strong']};
            border-radius: 4px;
            min-height: 24px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: {c['muted']};
        }}
        QScrollBar:horizontal {{
            background: {c['surface']};
            height: 12px;
            border: none;
        }}
        QScrollBar::handle:horizontal {{
            background: {c['border_strong']};
            border-radius: 4px;
            min-width: 24px;
        }}
        QGroupBox {{
            color: {c['text']};
            border: 1px solid {c['border']};
            border-radius: 4px;
            margin-top: 8px;
            padding-top: 16px;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 8px;
            padding: 0 4px;
        }}
        QProgressBar {{
            background-color: {c['surface']};
            border: 1px solid {c['border']};
            border-radius: 4px;
            text-align: center;
            color: {c['text']};
        }}
        QProgressBar::chunk {{
            background-color: {c['accent']};
            border-radius: 3px;
        }}
        QCheckBox {{
            color: {c['text']};
            spacing: 8px;
        }}
        QCheckBox::indicator {{
            width: 16px;
            height: 16px;
            border: 1px solid {c['border']};
            border-radius: 3px;
            background-color: {c['input_bg']};
        }}
        QCheckBox::indicator:checked {{
            background-color: {c['accent']};
            border-color: {c['accent']};
        }}
        QTabWidget::pane {{
            border: 1px solid {c['border']};
            background-color: {c['canvas']};
        }}
        QTabBar::tab {{
            background-color: {c['surface_alt']};
            color: {c['muted']};
            padding: 8px 16px;
            border: 1px solid {c['border']};
            border-bottom: none;
            margin-right: 2px;
        }}
        QTabBar::tab:selected {{
            background-color: {c['canvas']};
            color: {c['text']};
            border-bottom: 2px solid {c['accent']};
        }}
        QTabBar::tab:hover:!selected {{
            background-color: {c['hover']};
            color: {c['text']};
        }}
    """


def application_stylesheet(theme: str = "dark") -> str:
    """Build the common application stylesheet from the visual tokens."""
    c = colors_for(theme)
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
        {_common_widget_styles(c)}
    """


def workspace_topbar_stylesheet(theme: str = "dark") -> str:
    """Style the compact workspace identity bar."""
    c = colors_for(theme)
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


def dialog_stylesheet(theme: str = "dark") -> str:
    """Style modal dialogs."""
    c = colors_for(theme)
    return f"""
        QDialog {{
            background-color: {c['canvas']};
            color: {c['text']};
        }}
        QLabel {{
            color: {c['text']};
        }}
        {_common_widget_styles(c)}
    """


def button_stylesheet(theme: str = "dark", variant: str = "default") -> str:
    """Return QSS for a single button variant."""
    c = colors_for(theme)
    if variant == "primary":
        return f"""
            QPushButton {{
                background-color: {c['accent']};
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {c['accent_hover']}; }}
            QPushButton:pressed {{ background-color: {c['accent_pressed']}; }}
            QPushButton:disabled {{
                background-color: {c['disabled_bg']};
                color: {c['disabled_text']};
            }}
        """
    if variant == "icon":
        return f"""
            QToolButton {{
                border: none;
                font-size: 14px;
                color: {c['text']};
            }}
            QToolButton:hover {{
                background-color: {c['border']};
                border-radius: 4px;
            }}
        """
    if variant == "compact":
        return f"""
            QPushButton {{
                background-color: {c['disabled_bg']};
                color: {c['text']};
                border: none;
                padding: 2px 6px;
                border-radius: 3px;
                font-size: 11px;
            }}
            QPushButton:hover {{ background-color: {c['border_strong']}; }}
            QPushButton:pressed {{ background-color: {c['border']}; }}
        """
    return f"""
        QPushButton {{
            background-color: {c['disabled_bg']};
            color: {c['text']};
            border: none;
            padding: 8px 16px;
            border-radius: 4px;
        }}
        QPushButton:hover {{ background-color: {c['border_strong']}; }}
        QPushButton:pressed {{ background-color: {c['border']}; }}
    """


def table_stylesheet(theme: str = "dark") -> str:
    """Reusable table QSS."""
    c = colors_for(theme)
    return f"""
        QTableView, QTableWidget {{
            background: {c['canvas']};
            color: {c['text']};
            border: none;
            gridline-color: {c['gridline']};
        }}
        QTableView::item, QTableWidget::item {{ padding: 6px; }}
        QTableView::item:selected, QTableWidget::item:selected {{
            background: {c['selection']};
        }}
        QHeaderView::section {{
            background: {c['surface_alt']};
            color: {c['text']};
            padding: 8px;
            border: none;
            border-right: 1px solid {c['border']};
            font-weight: bold;
        }}
    """


def panel_header_stylesheet(theme: str = "dark") -> str:
    """Header bar used by workspace panels."""
    c = colors_for(theme)
    return f"background-color: {c['surface_alt']}; border-bottom: 1px solid {c['border']};"


def panel_title_stylesheet(theme: str = "dark", size: int = 14) -> str:
    """Panel title label styling."""
    c = colors_for(theme)
    return f"color: {c['text']}; font-size: {size}px; font-weight: bold;"


def muted_label_stylesheet(theme: str = "dark", size: int = 12) -> str:
    """Muted secondary label styling."""
    c = colors_for(theme)
    return f"color: {c['muted']}; font-size: {size}px;"


def menu_stylesheet(theme: str = "dark") -> str:
    """Context menu styling."""
    c = colors_for(theme)
    return (
        f"QMenu {{ background: {c['surface_alt']}; color: {c['text']};"
        f" border: 1px solid {c['border']}; padding: 4px; }}"
        f" QMenu::item {{ padding: 6px 24px; }}"
        f" QMenu::item:selected {{ background: {c['selection']}; }}"
    )


def metadata_panel_stylesheet(theme: str = "dark", changed_property: str = "metadataChanged") -> str:
    """Stylesheet for the metadata editor panel."""
    c = colors_for(theme)
    return (
        f"QWidget#cbzMetadataPanel {{ background: {c['canvas']}; color: {c['text']}; }}"
        f" QLineEdit, QTextEdit, QListWidget {{"
        f" background: {c['surface']}; color: {c['text']};"
        f" border: 1px solid {c['border']}; border-radius: 4px; padding: 4px; }}"
        f" QListWidget::item:selected {{ background: {c['selection']}; }}"
        f" QLineEdit[{changed_property}='true'] {{"
        f" border: 2px solid {c['accent']}; background: {c['changed_field']}; }}"
        f" QTextEdit[{changed_property}='true'] {{"
        f" border: 2px solid {c['accent']}; background: {c['changed_field']}; }}"
    )


def download_queue_panel_stylesheet(theme: str = "dark") -> str:
    """Stylesheet for the download queue panel."""
    c = colors_for(theme)
    return f"QWidget#downloadQueuePanel {{ background: {c['canvas']}; color: {c['text']}; }}"


def getcomics_panel_stylesheet(theme: str = "dark") -> str:
    """Stylesheet for the GetComics panel."""
    c = colors_for(theme)
    return (
        f"QWidget#getComicsPanel {{ background: {c['canvas']}; color: {c['text']}; }}"
        f" QLabel {{ color: {c['text']}; background: transparent; }}"
        f" QCheckBox {{ color: {c['text']}; }}"
        f" QLineEdit, QComboBox, QListWidget, QTableWidget {{"
        f" background: {c['surface']}; color: {c['text']};"
        f" border: 1px solid {c['border']}; border-radius: 4px; }}"
        f" QListWidget::item:selected {{ background: {c['selection']}; color: {c['text']}; }}"
        f" QHeaderView::section {{"
        f" background: {c['surface_alt']}; color: {c['text']};"
        f" border: 1px solid {c['border']}; padding: 4px; }}"
        f" QProgressBar {{"
        f" background: {c['surface']}; color: {c['text']};"
        f" border: 1px solid {c['border']}; border-radius: 4px; text-align: center; }}"
        f" QProgressBar::chunk {{ background: {c['accent']}; border-radius: 3px; }}"
        f" QGroupBox {{ color: {c['text']}; border: 1px solid {c['border']};"
        f" border-radius: 4px; margin-top: 8px; padding-top: 16px; }}"
        f" QGroupBox::title {{ subcontrol-origin: margin; left: 8px; padding: 0 4px; color: {c['text']}; }}"
    )


def cbl_preview_stylesheet(theme: str = "dark") -> str:
    """Stylesheet for the CBL preview frame."""
    c = colors_for(theme)
    return f"""
        QFrame#cblPreview {{
            background-color: {c['canvas']};
            color: {c['text']};
            border-top: 1px solid {c['border']};
        }}
        QPlainTextEdit {{
            background-color: {c['surface']};
            color: {c['text']};
            border: 1px solid {c['border']};
            border-radius: 4px;
        }}
    """


def syntax_colors(theme: str = "dark") -> dict:
    """Return syntax-highlighting colors for XML preview."""
    c = colors_for(theme)
    return {
        "tag": c["syntax_tag"],
        "attr": c["syntax_attr"],
        "quote": c["syntax_quote"],
    }
