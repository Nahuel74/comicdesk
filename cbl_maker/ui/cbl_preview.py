"""Read-only, resizable preview of the generated CBL document."""

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QToolButton,
    QVBoxLayout,
)


class _XmlHighlighter(QSyntaxHighlighter):
    """Small, non-invasive highlighter; the preview remains plain text."""

    def highlightBlock(self, text):
        tag = QTextCharFormat()
        tag.setForeground(QColor("#569cd6"))
        attr = QTextCharFormat()
        attr.setForeground(QColor("#9cdcfe"))
        quote = QTextCharFormat()
        quote.setForeground(QColor("#ce9178"))
        self.setFormat(0, len(text), QTextCharFormat())
        for start, end in self._matches(text, "<[^>]+>"):
            self.setFormat(start, end - start, tag)
        for start, end in self._matches(text, r"\b[\w:-]+(?=\s*=)"):
            self.setFormat(start, end - start, attr)
        for start, end in self._matches(text, r'"[^"]*"'):
            self.setFormat(start, end - start, quote)

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
        self.setObjectName("cblPreview")
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 4, 12, 4)
        root.setSpacing(4)

        bar = QHBoxLayout()
        title = QLabel("CBL Preview")
        title.setStyleSheet("color: #e0e0e0; font-weight: bold;")
        bar.addWidget(title)
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
        self._highlighter = _XmlHighlighter(self.text_edit.document())
        root.addWidget(self.text_edit, 1)
        self.setMinimumHeight(150)
        self._refresh_toggle_label()

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
