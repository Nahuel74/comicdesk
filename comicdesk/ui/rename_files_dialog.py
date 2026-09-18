"""Dialog to preview and confirm bulk CBZ renames from a metadata template."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from comicdesk.config import Config
from comicdesk.models import Comic
from comicdesk.ui.theme import button_stylesheet, dialog_stylesheet, muted_label_stylesheet
from comicdesk.ui.theme.tokens import colors_for
from comicdesk.utils.rename_template import (
    QUICK_PLACEHOLDERS,
    RenamePlanRow,
    RenameRowStatus,
    placeholder_help_lines,
    plan_apply_allowed,
    plan_renames,
)


def _preview_lines(row: RenamePlanRow) -> tuple[str, str]:
    """Return primary and secondary text for a preview list row."""
    current = row.old_path.name if row.old_path else "—"
    if row.proposed_path is not None:
        proposed = row.proposed_path.name
    else:
        proposed = "—"
    if row.status == RenameRowStatus.UNCHANGED:
        detail = "No change — already matches template"
    elif row.status == RenameRowStatus.OK:
        detail = f"Rename to: {proposed}"
    elif row.status == RenameRowStatus.EXCLUDED:
        detail = row.message or "Excluded"
    elif row.message:
        detail = f"{row.status.value}: {row.message}"
    else:
        detail = str(row.status.value)
    return current, detail


class RenameFilesDialog(QDialog):
    """Preview template-based renames for a set of local comics."""

    DEFAULT_TEMPLATE = "{Series} - {Number} ({Year})"

    def __init__(
        self,
        comics: list[Comic],
        config: Config | None = None,
        *,
        target_count: int,
        theme: str = "dark",
        parent=None,
    ):
        super().__init__(parent)
        self._comics = list(comics)
        self._config = config
        self._theme = theme
        self._rows: list[RenamePlanRow] = []
        self.setWindowTitle("Rename files")
        self.setMinimumSize(680, 520)
        self._build_ui(target_count)
        initial = ""
        if config is not None and getattr(config, "last_rename_template", ""):
            initial = config.last_rename_template
        if not initial:
            initial = self.DEFAULT_TEMPLATE
        self.template_edit.setText(initial)
        self._refresh_preview()

    def _build_ui(self, target_count: int) -> None:
        layout = QVBoxLayout(self)

        summary = QLabel(f"Preview rename for {target_count} local file(s).")
        layout.addWidget(summary)

        template_row = QHBoxLayout()
        self.template_edit = QLineEdit()
        self.template_edit.setPlaceholderText(self.DEFAULT_TEMPLATE)
        self.template_edit.textChanged.connect(self._refresh_preview)
        preset_btn = QPushButton("Example template")
        preset_btn.setToolTip("Replace with the example template")
        preset_btn.clicked.connect(
            lambda: self.template_edit.setText(self.DEFAULT_TEMPLATE)
        )
        template_row.addWidget(QLabel("Template"))
        template_row.addWidget(self.template_edit, 1)
        template_row.addWidget(preset_btn)
        layout.addLayout(template_row)

        pad_row = QHBoxLayout()
        pad_label = QLabel("Fallback issue digits")
        pad_label.setToolTip(
            "Used for {Number} only when ComicInfo Count is empty. "
            "When Count is set, padding is chosen automatically from the series size."
        )
        pad_row.addWidget(pad_label)
        self.issue_pad_spin = QSpinBox()
        self.issue_pad_spin.setRange(0, 9)
        self.issue_pad_spin.setSpecialValueText("No padding")
        self.issue_pad_spin.setToolTip(pad_label.toolTip())
        if self._config is not None:
            self.issue_pad_spin.setValue(
                max(0, int(getattr(self._config, "rename_issue_pad_width", 0) or 0))
            )
        self.issue_pad_spin.valueChanged.connect(self._refresh_preview)
        pad_row.addWidget(self.issue_pad_spin)
        pad_row.addStretch(1)
        layout.addLayout(pad_row)

        fields_label = QLabel("Insert field (click to add at cursor)")
        fields_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(fields_label)

        self._placeholder_buttons: list[QPushButton] = []
        placeholder_grid = QGridLayout()
        placeholder_grid.setHorizontalSpacing(8)
        placeholder_grid.setVerticalSpacing(8)
        columns = 4
        for index, (label, token) in enumerate(QUICK_PLACEHOLDERS):
            button = QPushButton(f"{label}\n{token}")
            button.setMinimumHeight(52)
            button.setToolTip(f"Insert {token}")
            button.clicked.connect(lambda _checked=False, t=token: self._insert_placeholder(t))
            self._placeholder_buttons.append(button)
            placeholder_grid.addWidget(button, index // columns, index % columns)
        layout.addLayout(placeholder_grid)

        for line in placeholder_help_lines():
            help_label = QLabel(line)
            help_label.setWordWrap(True)
            layout.addWidget(help_label)

        preview_label = QLabel("Preview")
        preview_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(preview_label)

        self.preview_list = QListWidget()
        self.preview_list.setSpacing(4)
        layout.addWidget(self.preview_list, 1)

        self.status_label = QLabel("")
        layout.addWidget(self.status_label)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        apply_btn = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
        if apply_btn is not None:
            apply_btn.setText("Apply")
        self.button_box.accepted.connect(self._try_accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)
        self.apply_theme(self._theme)

    def apply_theme(self, theme: str) -> None:
        self._theme = theme
        self.setStyleSheet(dialog_stylesheet(theme))
        self.status_label.setStyleSheet(muted_label_stylesheet(theme))
        chip_style = button_stylesheet(theme, "default") + """
            QPushButton { text-align: center; font-size: 11pt; padding: 10px 14px; }
        """
        for button in self._placeholder_buttons:
            button.setStyleSheet(chip_style)
        c = colors_for(theme)
        self.preview_list.setStyleSheet(
            f"""
            QListWidget {{
                background-color: {c['surface']};
                border: 1px solid {c['border']};
                border-radius: 4px;
                padding: 6px;
            }}
            QListWidget::item {{
                padding: 10px 8px;
                border-bottom: 1px solid {c['border']};
            }}
            """
        )

    def _insert_placeholder(self, token: str) -> None:
        edit = self.template_edit
        position = edit.cursorPosition()
        text = edit.text()
        edit.setText(text[:position] + token + text[position:])
        edit.setFocus()
        edit.setCursorPosition(position + len(token))

    def template_text(self) -> str:
        return self.template_edit.text().strip() or self.DEFAULT_TEMPLATE

    def issue_pad_width(self) -> int:
        return int(self.issue_pad_spin.value())

    def plan_rows(self) -> list[RenamePlanRow]:
        return list(self._rows)

    def _refresh_preview(self) -> None:
        self._rows = plan_renames(
            self._comics,
            self.template_text(),
            issue_pad_width=self.issue_pad_width(),
        )
        self.preview_list.clear()
        for row in self._rows:
            title, detail = _preview_lines(row)
            item = QListWidgetItem(f"{title}\n{detail}")
            item.setToolTip(
                f"Current: {row.old_path}\n"
                f"Proposed: {row.proposed_path or '—'}"
            )
            if row.status in (RenameRowStatus.INVALID, RenameRowStatus.COLLISION):
                item.setForeground(Qt.GlobalColor.red)
            elif row.status == RenameRowStatus.UNCHANGED:
                item.setForeground(Qt.GlobalColor.gray)
            self.preview_list.addItem(item)

        blocking = sum(
            1
            for row in self._rows
            if row.status in (RenameRowStatus.INVALID, RenameRowStatus.COLLISION)
        )
        excluded = sum(1 for row in self._rows if row.status == RenameRowStatus.EXCLUDED)
        ok = sum(1 for row in self._rows if row.status == RenameRowStatus.OK)
        unchanged = sum(1 for row in self._rows if row.status == RenameRowStatus.UNCHANGED)
        parts = [f"{ok} to rename", f"{unchanged} unchanged"]
        if excluded:
            parts.append(f"{excluded} excluded")
        if blocking:
            parts.append(f"{blocking} blocking issue(s)")
        self.status_label.setText("; ".join(parts))
        apply_btn = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
        if apply_btn is not None:
            apply_btn.setEnabled(plan_apply_allowed(self._rows))

    def _try_accept(self) -> None:
        if plan_apply_allowed(self._rows):
            self.accept()
