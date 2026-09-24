"""Dialog to preview and confirm bulk archive page renames from a template."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable

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
from comicdesk.utils.page_rename_template import (
    DEFAULT_PAGE_TEMPLATE,
    PAGE_QUICK_PLACEHOLDERS,
    RenamePageMemberRow,
    page_placeholder_help_lines,
    plan_page_member_renames,
    plan_page_rename_apply_allowed,
)
from comicdesk.utils.rename_template import RenameRowStatus


def _preview_lines(row: RenamePageMemberRow) -> tuple[str, str]:
    current = row.old_name or "—"
    proposed = row.proposed_name or "—"
    if row.status == RenameRowStatus.UNCHANGED:
        return current, "No change — already matches template"
    if row.status == RenameRowStatus.OK:
        return current, f"Rename to: {proposed}"
    if row.message:
        return current, f"{row.status.value}: {row.message}"
    return current, str(row.status.value)


class RenamePagesDialog(QDialog):
    """Preview template-based renames for image members inside comic archives."""

    def __init__(
        self,
        comics: list[Comic],
        config: Config | None = None,
        *,
        target_count: int,
        theme: str = "dark",
        metadata_for: Callable[[Comic], Comic | None] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._comics = list(comics)
        self._config = config
        self._theme = theme
        self._metadata_for = metadata_for
        self._rows: list[RenamePageMemberRow] = []
        self.setWindowTitle("Rename pages")
        self.setMinimumSize(680, 520)
        self._build_ui(target_count)
        initial = self._initial_template()
        self.template_edit.setText(initial)
        self._refresh_preview()

    def _initial_template(self) -> str:
        if self._config is None:
            return DEFAULT_PAGE_TEMPLATE
        stored = getattr(self._config, "last_rename_page_template", "") or ""
        if stored:
            return stored
        return DEFAULT_PAGE_TEMPLATE

    def _build_ui(self, target_count: int) -> None:
        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(f"Preview page renames for {target_count} local archive(s).")
        )

        template_row = QHBoxLayout()
        self.template_edit = QLineEdit()
        self.template_edit.setPlaceholderText(DEFAULT_PAGE_TEMPLATE)
        self.template_edit.textChanged.connect(self._refresh_preview)
        preset_btn = QPushButton("Example template")
        preset_btn.clicked.connect(
            lambda: self.template_edit.setText(DEFAULT_PAGE_TEMPLATE)
        )
        template_row.addWidget(QLabel("Template"))
        template_row.addWidget(self.template_edit, 1)
        template_row.addWidget(preset_btn)
        layout.addLayout(template_row)

        pad_row = QHBoxLayout()
        issue_label = QLabel("Fallback issue digits")
        issue_label.setToolTip(
            "Used for {Number} when ComicInfo Count is empty (same as Library rename)."
        )
        pad_row.addWidget(issue_label)
        self.issue_pad_spin = QSpinBox()
        self.issue_pad_spin.setRange(0, 9)
        self.issue_pad_spin.setSpecialValueText("No padding")
        if self._config is not None:
            self.issue_pad_spin.setValue(
                max(0, int(getattr(self._config, "rename_issue_pad_width", 0) or 0))
            )
        self.issue_pad_spin.valueChanged.connect(self._refresh_preview)
        pad_row.addWidget(self.issue_pad_spin)

        page_label = QLabel("Page digits")
        page_label.setToolTip("Leading zeros for {Page} when the template has no :digits.")
        pad_row.addWidget(page_label)
        self.page_pad_spin = QSpinBox()
        self.page_pad_spin.setRange(0, 9)
        self.page_pad_spin.setSpecialValueText("No padding")
        if self._config is not None:
            self.page_pad_spin.setValue(
                max(0, int(getattr(self._config, "rename_page_pad_width", 0) or 0))
            )
        self.page_pad_spin.valueChanged.connect(self._refresh_preview)
        pad_row.addWidget(self.page_pad_spin)
        pad_row.addStretch(1)
        layout.addLayout(pad_row)

        fields_label = QLabel("Insert field (click to add at cursor)")
        fields_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(fields_label)

        self._placeholder_buttons: list[QPushButton] = []
        grid = QGridLayout()
        columns = 3
        for index, (label, token) in enumerate(PAGE_QUICK_PLACEHOLDERS):
            button = QPushButton(f"{label}\n{token}")
            button.setMinimumHeight(52)
            button.clicked.connect(
                lambda _checked=False, t=token: self._insert_placeholder(t)
            )
            self._placeholder_buttons.append(button)
            grid.addWidget(button, index // columns, index % columns)
        layout.addLayout(grid)

        for line in page_placeholder_help_lines():
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
        return self.template_edit.text().strip() or DEFAULT_PAGE_TEMPLATE

    def issue_pad_width(self) -> int:
        return int(self.issue_pad_spin.value())

    def page_pad_width(self) -> int:
        return int(self.page_pad_spin.value())

    def plan_rows(self) -> list[RenamePageMemberRow]:
        return list(self._rows)

    def _refresh_preview(self) -> None:
        self._rows = plan_page_member_renames(
            self._comics,
            self.template_text(),
            issue_pad_width=self.issue_pad_width(),
            page_pad_width=self.page_pad_width(),
            metadata_for=self._metadata_for,
        )
        self.preview_list.clear()
        by_comic: dict[str, list[RenamePageMemberRow]] = defaultdict(list)
        for row in self._rows:
            key = str(row.comic.path)
            by_comic[key].append(row)

        for comic in self._comics:
            key = str(comic.path)
            group = by_comic.get(key)
            if not group:
                continue
            header = QListWidgetItem(comic.path.name)
            header.setFlags(Qt.ItemFlag.NoItemFlags)
            self.preview_list.addItem(header)
            for row in group:
                title, detail = _preview_lines(row)
                item = QListWidgetItem(f"  {title}\n  {detail}")
                self._style_preview_item(item, row.status)
                self.preview_list.addItem(item)

        blocking = sum(
            1
            for row in self._rows
            if row.status in (RenameRowStatus.INVALID, RenameRowStatus.COLLISION)
        )
        ok = sum(1 for row in self._rows if row.status == RenameRowStatus.OK)
        unchanged = sum(1 for row in self._rows if row.status == RenameRowStatus.UNCHANGED)
        parts = [f"{ok} to rename", f"{unchanged} unchanged"]
        if blocking:
            parts.append(f"{blocking} blocking issue(s)")
        self.status_label.setText("; ".join(parts))
        apply_btn = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
        if apply_btn is not None:
            apply_btn.setEnabled(plan_page_rename_apply_allowed(self._rows))

    def _style_preview_item(self, item: QListWidgetItem, status: RenameRowStatus) -> None:
        if status in (RenameRowStatus.INVALID, RenameRowStatus.COLLISION):
            item.setForeground(Qt.GlobalColor.red)
        elif status in (RenameRowStatus.UNCHANGED, RenameRowStatus.EXCLUDED):
            item.setForeground(Qt.GlobalColor.gray)

    def _try_accept(self) -> None:
        if plan_page_rename_apply_allowed(self._rows):
            self.accept()
