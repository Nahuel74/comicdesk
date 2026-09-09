"""Read-only, resizable preview of the generated CBL document."""

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QToolButton,
    QVBoxLayout,
)

from comicdesk.ui.theme import (
    button_stylesheet,
    cbl_preview_stylesheet,
    colors_for,
    panel_title_stylesheet,
    syntax_colors,
)


class _XmlHighlighter(QSyntaxHighlighter):
    """Small, non-invasive highlighter; the preview remains plain text."""

    def __init__(self, document, theme: str = "dark"):
        super().__init__(document)
        self._theme = theme
        self._apply_colors()

    def set_theme(self, theme: str) -> None:
        self._theme = theme
        self._apply_colors()
        self.rehighlight()

    def _apply_colors(self) -> None:
        colors = syntax_colors(self._theme)
        self._tag = QTextCharFormat()
        self._tag.setForeground(QColor(colors["tag"]))
        self._attr = QTextCharFormat()
        self._attr.setForeground(QColor(colors["attr"]))
        self._quote = QTextCharFormat()
        self._quote.setForeground(QColor(colors["quote"]))

    def highlightBlock(self, text):
        self.setFormat(0, len(text), QTextCharFormat())
        for start, end in self._matches(text, "<[^>]+>"):
            self.setFormat(start, end - start, self._tag)
        for start, end in self._matches(text, r"\b[\w:-]+(?=\s*=)"):
            self.setFormat(start, end - start, self._attr)
        for start, end in self._matches(text, r'"[^"]*"'):
            self.setFormat(start, end - start, self._quote)

    @staticmethod
    def _matches(text, pattern):
        import re
        return [(m.start(), m.end()) for m in re.finditer(pattern, text)]


class CBLPreview(QFrame):
    """Read-only CBL viewer with explicit copy, selection and sizing actions."""

    expanded_changed = Signal(bool)
    maximize_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._expanded = True
        self._theme = "dark"
        self.setObjectName("cblPreview")
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 4, 12, 4)
        root.setSpacing(4)

        bar = QHBoxLayout()
        self.title_label = QLabel("CBL Preview")
        bar.addWidget(self.title_label)
        bar.addStretch()
        self.select_btn = QPushButton("Select all")
        self.select_btn.setToolTip("Select all preview text")
        self.select_btn.clicked.connect(self.select_all)
        bar.addWidget(self.select_btn)
        self.copy_btn = QPushButton("Copy")
        self.copy_btn.setToolTip("Copy the generated CBL")
        self.copy_btn.clicked.connect(self.copy)
        bar.addWidget(self.copy_btn)
        self.maximize_btn = QToolButton()
        self.maximize_btn.setText("⤢")
        self.maximize_btn.setToolTip("Maximize preview")
        self.maximize_btn.clicked.connect(self.maximize)
        bar.addWidget(self.maximize_btn)
        self.toggle_btn = QToolButton()
        self.toggle_btn.clicked.connect(self.toggle_expanded)
        bar.addWidget(self.toggle_btn)
        root.addLayout(bar)

        self.text_edit = QPlainTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setPlaceholderText("CBL preview will appear here...")
        self.text_edit.setLineWrapMode(QPlainTextEdit.NoWrap)
        font = QFont("DejaVu Sans Mono", 10)
        font.setStyleHint(QFont.Monospace)
        self.text_edit.setFont(font)
        self._highlighter = _XmlHighlighter(self.text_edit.document(), self._theme)
        root.addWidget(self.text_edit, 1)
        self.setMinimumHeight(150)
        self._refresh_toggle_label()
        self.apply_theme(self._theme)

    def apply_theme(self, theme: str) -> None:
        """Re-apply visual tokens for the active theme."""
        self._theme = theme
        self.setStyleSheet(cbl_preview_stylesheet(theme))
        self.title_label.setStyleSheet(panel_title_stylesheet(theme, size=12))
        default_btn = button_stylesheet(theme, "default")
        self.select_btn.setStyleSheet(default_btn)
        self.copy_btn.setStyleSheet(default_btn)
        icon_btn = button_stylesheet(theme, "icon")
        self.maximize_btn.setStyleSheet(icon_btn)
        self.toggle_btn.setStyleSheet(icon_btn)
        self._highlighter.set_theme(theme)

    def set_content(self, content):
        """Replace generated content without changing expansion state."""
        self.text_edit.setPlainText(content or "")

    update_content = set_content

    def toPlainText(self):
        return self.text_edit.toPlainText()

    def setPlainText(self, content):
        self.set_content(content)

    def isReadOnly(self):
        return self.text_edit.isReadOnly()

    def copy(self):
        self.text_edit.copy()

    def select_all(self):
        self.text_edit.selectAll()

    def is_expanded(self):
        return self._expanded

    @property
    def expanded(self):
        return self._expanded

    def set_expanded(self, expanded):
        expanded = bool(expanded)
        if expanded == self._expanded:
            return
        self._expanded = expanded
        self.text_edit.setVisible(expanded)
        self._refresh_toggle_label()
        self.expanded_changed.emit(expanded)

    def toggle_expanded(self):
        self.set_expanded(not self._expanded)

    def maximize(self):
        self.set_expanded(True)
        self.maximize_requested.emit()

    def _refresh_toggle_label(self):
        self.toggle_btn.setText("⌃" if self._expanded else "⌄")
        self.toggle_btn.setToolTip("Collapse preview" if self._expanded else "Expand preview")
