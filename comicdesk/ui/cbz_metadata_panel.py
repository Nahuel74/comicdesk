"""Themed editor for metadata belonging to one selected comic archive."""
from __future__ import annotations
from pathlib import Path
import logging
from PySide6.QtCore import QCoreApplication, QSize, Qt, Signal
from PySide6.QtGui import QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QApplication,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTextEdit,
    QTableView,
    QVBoxLayout,
    QWidget,
    QSplitter,
)
from comicdesk.ui.metadata_instance_model import MetadataInstanceModel
from comicdesk.models import Comic, ComicVineVolume
from comicdesk.services.comicinfo import FIELD_TAGS, join_web_links
from comicdesk.services.identification import STATUS_CANDIDATES, STATUS_EMPTY
from comicdesk.services.identification import issue_needs_hydrate, issue_needs_volume_resolve
from comicdesk.services.metadata_session import MetadataSession, BATCH_SERIES_FIELDS
from comicdesk.ui.cbz_metadata_workers import MetadataSearchWorker, MetadataHydrateWorker, MetadataWriteWorker
from comicdesk.ui.comicvine_candidate_widgets import (
    CANDIDATE_ROW_HEIGHT,
    COVER_HEIGHT,
    COVER_WIDTH,
    CandidateResultRow,
    CoverLoader,
    candidate_lines,
)
from comicdesk.ui.theme import (
    SPACING,
    button_stylesheet,
    colors_for,
    metadata_panel_stylesheet,
    muted_label_stylesheet,
)
MULTILINE_FIELDS = {"summary", "notes", "review"}
ID_FIELDS = (("Series ID", "cv_series_id"), ("Issue ID", "cv_issue_id"))
CHANGED_PROPERTY = "metadataChanged"
WORKER_JOIN_TIMEOUT_MS = 5000
FIELD_LABELS = {name: label for label, name in FIELD_TAGS}
METADATA_GROUPS = (
    ("Identifiers", ("cv_series_id", "cv_issue_id")),
    (
        "Publication",
        (
            "title",
            "series_name",
            "issue_number",
            "volume",
            "count",
            "alternate_series",
            "alternate_number",
            "alternate_count",
            "year",
            "month",
            "day",
        ),
    ),
    ("Story", ("story_arc", "story_arc_number", "summary", "notes", "review")),
    (
        "Credits",
        (
            "writer",
            "penciller",
            "inker",
            "colorist",
            "letterer",
            "cover_artist",
            "editor",
            "translator",
        ),
    ),
    (
        "Classification",
        (
            "publisher",
            "imprint",
            "genre",
            "tags",
            "page_count",
            "language_iso",
            "format",
            "black_and_white",
            "manga",
            "age_rating",
            "community_rating",
        ),
    ),
    (
        "Universe",
        ("characters", "teams", "locations", "main_character_or_team", "series_group"),
    ),
    ("Other", ("scan_information", "gtin", "web_links")),
)
logger = logging.getLogger(__name__)


class ComicInstanceList(QListWidget):
    """Sidebar list with a small compatibility shim for the former selector API."""

    def setCurrentIndex(self, index):
        self.setCurrentRow(index)


class CbzMetadataPanel(QWidget):
    metadata_saved = Signal(object, object)
    status_message = Signal(str)
    dirty_changed = Signal(bool)
    comic_focus_requested = Signal(object)
    def __init__(self, comic=None, config=None, parent=None):
        super().__init__(parent)
        self.session = None
        self.config = config
        self.comic = None
        self._proposal = None
        self._search_worker = self._hydrate_worker = self._write_worker = None
        self._request_token, self._path_key, self._loading = 0, "", False
        self._pending_comic = None; self._has_pending_comic = False
        self._write_session = None; self._write_completion = None
        self._changed_fields: set[str] = set()
        self._pre_apply_values: dict[str, object] = {}
        self._theme = "dark"
        self._cover_loaders: list[CoverLoader] = []
        self._extra_sessions: dict[str, MetadataSession] = {}
        self._write_queue: list[MetadataSession] = []
        self._write_queue_total = 0
        self._write_queue_succeeded = 0
        self._write_queue_failed = 0
        self._body_splitter_sizes: list[int] | None = None
        self._build_ui()
        if comic is not None:
            self.set_comic(comic)
    def _build_ui(self):
        self.setObjectName("cbzMetadataPanel")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(SPACING["md"], SPACING["sm"], SPACING["md"], SPACING["md"])
        outer.setSpacing(SPACING["sm"])

        self.title_label = QLabel("Selected comic")
        self.title_label.hide()

        working_set = QGroupBox(
            "Working set — click a row to edit one file; Ctrl/Shift to select several for shared series"
        )
        working_layout = QVBoxLayout(working_set)
        filter_row = QHBoxLayout()
        self.instance_filter = QLineEdit()
        self.instance_filter.setPlaceholderText("Filter files in folder…")
        self.instance_filter.textChanged.connect(self._on_instance_filter_changed)
        filter_row.addWidget(self.instance_filter, 1)
        working_layout.addLayout(filter_row)

        self.working_set_context_label = QLabel("")
        self.working_set_context_label.setWordWrap(True)
        working_layout.addWidget(self.working_set_context_label)

        self.instance_model = MetadataInstanceModel(self)
        self.instance_table = QTableView()
        self.instance_table.setModel(self.instance_model)
        self.instance_table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.instance_table.setSelectionMode(QTableView.SelectionMode.ExtendedSelection)
        self.instance_table.verticalHeader().setVisible(False)
        header = self.instance_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in (1, 2, 3):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self.instance_table.setMinimumHeight(260)
        self.instance_table.selectionModel().currentRowChanged.connect(self._on_instance_row_changed)
        self.instance_table.selectionModel().selectionChanged.connect(
            self._on_instance_selection_changed
        )
        working_layout.addWidget(self.instance_table)

        self.comic_selector = ComicInstanceList()
        self.comic_selector.hide()
        self.comic_selector.currentItemChanged.connect(
            lambda *_: self._selector_changed(self.comic_selector.currentRow())
        )
        working_layout.addWidget(self.comic_selector)
        outer.addWidget(working_set)

        body_splitter = QSplitter(Qt.Orientation.Horizontal)

        editor = QWidget()
        editor_layout = QVBoxLayout(editor)
        editor_layout.setContentsMargins(0, 0, SPACING["sm"], 0)
        self.editor_stack = QStackedWidget()

        self.single_editor_page = QWidget()
        single_layout = QVBoxLayout(self.single_editor_page)
        single_layout.setContentsMargins(0, 0, 0, 0)
        self.editing_header_label = QLabel("No file selected")
        self.editing_header_label.setWordWrap(True)
        single_layout.addWidget(self.editing_header_label)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        host = QWidget()
        host_layout = QVBoxLayout(host)
        host_layout.setSpacing(SPACING["md"])
        self.inputs = {}
        self.field_inputs = self.inputs
        self.form_layout = QFormLayout()
        default_open = {"Identifiers", "Publication"}
        for group_title, field_names in METADATA_GROUPS:
            group = QGroupBox(group_title)
            group.setCheckable(True)
            group.setChecked(group_title in default_open)
            group.toggled.connect(lambda checked, box=group: box.setFlat(not checked))
            group_form = QFormLayout(group)
            group_form.setFieldGrowthPolicy(
                QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
            )
            group_form.setSpacing(SPACING["sm"])
            for name in field_names:
                if name in ("cv_series_id", "cv_issue_id"):
                    label = next(lbl for lbl, fld in ID_FIELDS if fld == name)
                else:
                    label = FIELD_LABELS.get(name, name)
                self._add_input(label, name, group_form)
            host_layout.addWidget(group)
        self.scroll.setWidget(host)
        single_layout.addWidget(self.scroll, 1)
        self.editor_stack.addWidget(self.single_editor_page)

        self.batch_editor_page = QWidget()
        batch_page_layout = QVBoxLayout(self.batch_editor_page)
        batch_page_layout.setContentsMargins(0, 0, 0, 0)
        batch_page_layout.setSpacing(SPACING["sm"])
        self.batch_header_label = QLabel("Select multiple files in the table")
        self.batch_header_label.setWordWrap(True)
        batch_page_layout.addWidget(self.batch_header_label)
        batch_group = QGroupBox("Shared series metadata")
        batch_layout = QVBoxLayout(batch_group)
        batch_layout.setContentsMargins(SPACING["md"], SPACING["md"], SPACING["md"], SPACING["md"])
        batch_layout.setSpacing(SPACING["sm"])
        self.batch_inputs: dict[str, QLineEdit] = {}
        batch_form = QFormLayout()
        batch_form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
        )
        batch_form.setHorizontalSpacing(SPACING["md"])
        batch_form.setVerticalSpacing(SPACING["sm"])
        batch_field_labels = {
            "cv_series_id": "Series ID",
            "series_name": FIELD_LABELS.get("series_name", "Series"),
            "volume": FIELD_LABELS.get("volume", "Volume"),
            "publisher": FIELD_LABELS.get("publisher", "Publisher"),
        }
        for name in BATCH_SERIES_FIELDS:
            label = batch_field_labels.get(name, name)
            widget = QLineEdit()
            self.batch_inputs[name] = widget
            batch_form.addRow(QLabel(label), widget)
        batch_layout.addLayout(batch_form)
        batch_hint = QLabel("Written to each selected archive when you save.")
        batch_hint.setWordWrap(True)
        self.batch_hint_label = batch_hint
        batch_layout.addWidget(batch_hint)
        apply_row = QHBoxLayout()
        apply_row.addStretch(1)
        self.apply_to_selected_button = self._button(
            "Apply to selected", self.apply_batch_to_selected
        )
        self.apply_to_selected_button.setProperty("primary", True)
        self.apply_to_selected_button.setMinimumWidth(240)
        apply_row.addWidget(self.apply_to_selected_button)
        batch_layout.addLayout(apply_row)
        batch_page_layout.addWidget(batch_group)

        self.batch_files_group = QGroupBox("Selected files")
        batch_files_layout = QVBoxLayout(self.batch_files_group)
        batch_files_layout.setContentsMargins(SPACING["sm"], SPACING["sm"], SPACING["sm"], SPACING["sm"])
        self.batch_selection_list = QListWidget()
        self.batch_selection_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.batch_selection_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        batch_files_layout.addWidget(self.batch_selection_list)
        batch_page_layout.addWidget(self.batch_files_group, 1)
        self.editor_stack.addWidget(self.batch_editor_page)

        editor_layout.addWidget(self.editor_stack, 1)
        body_splitter.addWidget(editor)

        cv_panel = QGroupBox("Comic Vine")
        cv_layout = QVBoxLayout(cv_panel)
        cv_layout.setSpacing(SPACING["sm"])
        self.state_label = QLabel("No comic selected")
        self.comicvine_status_label = self.state_label
        self.state_label.setWordWrap(True)
        cv_layout.addWidget(self.state_label)
        self.proposals_label = QLabel("Proposals")
        cv_layout.addWidget(self.proposals_label)
        self.candidates_list = QListWidget()
        self.candidate_list = self.candidates_list
        self.candidates_list.setMinimumHeight(160)
        self.candidates_list.setIconSize(QSize(COVER_WIDTH, COVER_HEIGHT))
        self.candidates_list.itemSelectionChanged.connect(self._candidate_selected)
        cv_layout.addWidget(self.candidates_list, 1)
        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        cv_layout.addWidget(self.status_label)
        search_row = QHBoxLayout()
        self.search_button = self._button("1. Search", self.search)
        self.search_btn = self.search_button
        self.search_progress = QProgressBar()
        self.search_progress.setRange(0, 0)
        self.search_progress.setFixedHeight(8)
        self.search_progress.setTextVisible(False)
        self.search_progress.hide()
        search_row.addWidget(self.search_button)
        search_row.addWidget(self.search_progress, 1)
        cv_layout.addLayout(search_row)
        self.apply_button = self._button("2. Apply", self.apply_proposal)
        self.apply_btn = self.apply_button
        self.discard_button = self._button("3. Discard draft", self.discard)
        self.discard_btn = self.discard_button
        self.save_button = self._button("4. Save to archive", self.save)
        self.save_btn = self.save_button
        self.save_button.setProperty("primary", True)
        for button in (
            self.apply_button,
            self.discard_button,
            self.save_button,
        ):
            cv_layout.addWidget(button)
        cv_panel.setMinimumWidth(300)
        cv_panel.setMaximumWidth(380)
        self.cv_panel = cv_panel
        self.body_splitter = body_splitter
        body_splitter.addWidget(cv_panel)
        body_splitter.setStretchFactor(0, 3)
        body_splitter.setStretchFactor(1, 1)
        body_splitter.setSizes([700, 340])
        outer.addWidget(body_splitter, 1)
        self._digit_shortcuts: list[QShortcut] = []
        self._install_digit_shortcuts()
        self._set_action_state()
        self.apply_theme(self._theme)

    def apply_theme(self, theme: str) -> None:
        """Re-apply visual tokens for the active theme."""
        self._theme = theme
        c = colors_for(theme)
        self.setStyleSheet(metadata_panel_stylesheet(theme, CHANGED_PROPERTY))
        self.title_label.setStyleSheet(
            f"font-size: 15px; font-weight: 600; color: {c['text']};"
        )
        self.state_label.setStyleSheet(muted_label_stylesheet(theme))
        self.proposals_label.setStyleSheet(
            f"color: {c['text']}; font-weight: 600;"
        )
        self.status_label.setStyleSheet(muted_label_stylesheet(theme))
        self.working_set_context_label.setStyleSheet(muted_label_stylesheet(theme))
        self.editing_header_label.setStyleSheet(
            f"font-size: 14px; font-weight: 600; color: {c['text']};"
        )
        self.batch_header_label.setStyleSheet(
            f"font-size: 13px; font-weight: 600; color: {c['text']};"
        )
        self.batch_hint_label.setStyleSheet(muted_label_stylesheet(theme))
        default_btn = button_stylesheet(theme, "default")
        primary_btn = button_stylesheet(theme, "primary")
        for button in (
            self.search_button,
            self.apply_button,
            self.discard_button,
        ):
            button.setStyleSheet(default_btn)
        self.apply_to_selected_button.setStyleSheet(primary_btn)
        self.save_button.setStyleSheet(primary_btn)
    def _add_input(self, label, name, form_layout: QFormLayout | None = None):
        target = form_layout or self.form_layout
        if name in MULTILINE_FIELDS:
            widget = QTextEdit()
            widget.setMaximumHeight(90)
            widget.textChanged.connect(
                lambda n=name, w=widget: self._field_changed(n, w.toPlainText())
            )
        else:
            widget = QLineEdit()
            widget.textChanged.connect(lambda value, n=name: self._field_changed(n, value))
        self.inputs[name] = widget
        setattr(self, f"{name}_input", widget)
        target.addRow(QLabel(label), widget)

    def _on_instance_filter_changed(self, text: str) -> None:
        self.instance_model.set_filter(text)

    def _selected_comics(self) -> list[Comic]:
        selection = self.instance_table.selectionModel()
        if selection is None:
            return []
        comics: list[Comic] = []
        for index in selection.selectedRows():
            comic = self.instance_model.comic_at(index.row())
            if comic is not None:
                comics.append(comic)
        return comics

    def _on_instance_row_changed(self, current, _previous) -> None:
        if not current.isValid():
            self._refresh_working_set_context()
            return
        comic = self.instance_model.comic_at(current.row())
        if comic is None:
            self._refresh_working_set_context()
            return
        if comic is self.comic:
            self._refresh_working_set_context()
            return
        if not self.set_comic(comic):
            self._sync_instance_table()
        else:
            logger.info("metadata_instance_selected path=%s", self._path_key)
            self.comic_focus_requested.emit(comic)

    def _on_instance_selection_changed(self, _selected, _deselected) -> None:
        self._refresh_working_set_context()
        self._set_action_state()

    def _refresh_working_set_context(self) -> None:
        selected = self._selected_comics()
        count = len(selected)
        if self.comic is not None and getattr(self.comic, "path", None):
            editing_name = self.comic.path.name
        else:
            editing_name = "—"
        parts: list[str] = []
        if count == 0:
            parts.append("No files selected")
        elif count == 1:
            parts.append("1 file selected")
        else:
            parts.append(f"{count} files selected")
        parts.append(f"Editing: {editing_name}")
        if count != 1:
            parts.append("Comic Vine search: one file only")
        self.working_set_context_label.setText(" · ".join(parts))
        if self.comic is not None:
            self.editing_header_label.setText(f"Editing: {editing_name}")
        else:
            self.editing_header_label.setText("No file selected")
        if count >= 2:
            self.apply_to_selected_button.setText(f"Save to {count} selected")
            self.batch_header_label.setText(
                f"Shared series for {count} selected files"
            )
        else:
            self.apply_to_selected_button.setText("Apply to selected")
            self.batch_header_label.setText("Select multiple files in the table")
        self._refresh_batch_selection_list(selected)

    def _refresh_batch_selection_list(self, selected: list[Comic]) -> None:
        self.batch_selection_list.clear()
        count = len(selected)
        if count >= 2:
            self.batch_files_group.setTitle(f"Selected files ({count})")
        else:
            self.batch_files_group.setTitle("Selected files")
        if count < 2:
            return
        active_key = self._path_key
        for comic in selected:
            path = getattr(comic, "path", None)
            name = path.name if path else "—"
            if active_key and self._comic_path_key(comic) == active_key:
                name = f"▸ {name}"
            issue = (getattr(comic, "issue_number", "") or "").strip()
            series = (getattr(comic, "series_name", "") or "").strip()
            if series or issue:
                detail = series or "—"
                if issue:
                    detail = f"{detail} #{issue}" if series else f"#{issue}"
                name = f"{name} — {detail}"
            self.batch_selection_list.addItem(name)

    def _refresh_save_button_label(self) -> None:
        pending = len(self._dirty_sessions_queue())
        if pending > 1:
            self.save_button.setText(f"4. Save {pending} archives")
        else:
            self.save_button.setText("4. Save to archive")

    def _session_for_comic(self, comic: Comic) -> MetadataSession:
        key = self._comic_path_key(comic)
        if self.comic is comic and self.session is not None:
            return self.session
        if key not in self._extra_sessions:
            self._extra_sessions[key] = MetadataSession(comic)
        return self._extra_sessions[key]

    def _any_dirty(self) -> bool:
        if self.session and self.session.is_dirty:
            return True
        return any(session.is_dirty for session in self._extra_sessions.values())

    def _batch_field_values(self) -> dict[str, str]:
        values: dict[str, str] = {}
        for name in BATCH_SERIES_FIELDS:
            widget = self.batch_inputs.get(name)
            if widget is None:
                continue
            values[name] = widget.text()
        return values

    def _sync_comicvine_panel_visibility(self, multi_selection: bool) -> None:
        if multi_selection:
            if self.cv_panel.isVisible():
                self._body_splitter_sizes = self.body_splitter.sizes()
            self.cv_panel.hide()
            total = max(sum(self.body_splitter.sizes()), 1)
            self.body_splitter.setSizes([total, 0])
            return
        self.cv_panel.show()
        if self._body_splitter_sizes and len(self._body_splitter_sizes) >= 2:
            self.body_splitter.setSizes(self._body_splitter_sizes)
        else:
            self.body_splitter.setSizes([700, 340])

    def _batch_would_change(self, session: MetadataSession, fields: dict[str, str]) -> bool:
        current = session.values()
        for name in BATCH_SERIES_FIELDS:
            left = str(current.get(name, "") or "")
            right = str(fields.get(name, "") or "")
            if left != right:
                return True
        return False

    def apply_batch_to_selected(self) -> None:
        if self._write_worker is not None:
            return
        selected = self._selected_comics()
        if len(selected) < 2:
            return
        fields = self._batch_field_values()
        targets: list[tuple[Comic, MetadataSession]] = []
        for comic in selected:
            session = self._session_for_comic(comic)
            if self._batch_would_change(session, fields):
                targets.append((comic, session))
        if not targets:
            self._set_status("No changes to apply to the selected files")
            return
        count = len(targets)
        archive_word = "archive" if count == 1 else "archives"
        answer = QMessageBox.question(
            self,
            "Apply to selected",
            f"Save shared series metadata to {count} {archive_word}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        sessions_to_write: list[MetadataSession] = []
        for comic, session in targets:
            session.apply_fields(fields)
            key = self._comic_path_key(comic)
            if session.is_dirty:
                self._extra_sessions[key] = session
                sessions_to_write.append(session)
            self.instance_model.notify_comic_changed(comic)
        if self.comic in selected:
            self._populate_form()
        self._emit_dirty()
        self._set_action_state()
        self._refresh_working_set_context()
        if not sessions_to_write:
            self._set_status("No changes to save")
            return
        self._write_queue = sessions_to_write
        self._write_queue_total = len(sessions_to_write)
        self._write_queue_succeeded = 0
        self._write_queue_failed = 0
        self._start_next_write()
        logger.info(
            "metadata_batch_applied count=%s series_id=%s",
            len(sessions_to_write),
            fields.get("cv_series_id", ""),
        )

    def _dirty_sessions_queue(self) -> list[MetadataSession]:
        queue: list[MetadataSession] = []
        seen: set[str] = set()
        for key, session in self._extra_sessions.items():
            if session.is_dirty and key not in seen:
                queue.append(session)
                seen.add(key)
        if self.session and self.session.is_dirty:
            key = self._path_key
            if key and key not in seen:
                queue.append(self.session)
        return queue

    def _start_next_write(self) -> bool:
        if not self._write_queue:
            return False
        session = self._write_queue[0]
        raw_path = session.draft.path
        if not raw_path or str(raw_path) == ".":
            self._set_status(
                "Cannot save metadata: no local comic file path is available"
            )
            return False
        self._request_token += 1
        token = self._request_token
        path_key = self._comic_path_key(session.original)
        self._write_session = session
        self._write_completion = None
        self._write_worker = MetadataWriteWorker(
            session.snapshot(), token=token, path=Path(raw_path)
        )
        worker = self._write_worker
        worker.finished.connect(
            lambda saved, w=worker, t=token, p=path_key: self._write_finished(
                saved, w, t, p
            )
        )
        worker.error.connect(
            lambda message, w=worker, t=token, p=path_key: self._write_error(
                message, w, t, p
            )
        )
        recorder = lambda value, w=worker: self._record_write_completion(w, True, value)
        error_recorder = lambda message, w=worker: self._record_write_completion(
            w, False, message
        )
        try:
            worker.finished.connect(recorder, Qt.ConnectionType.DirectConnection)
            worker.error.connect(error_recorder, Qt.ConnectionType.DirectConnection)
        except TypeError:
            pass
        index = self._write_queue_total - len(self._write_queue) + 1
        if self._write_queue_total > 1:
            self._set_status(f"Saving metadata ({index}/{self._write_queue_total})…")
            if len(self._selected_comics()) >= 2:
                self.batch_header_label.setText(
                    f"Saving {index} of {self._write_queue_total}…"
                )
        else:
            self._set_status("Saving metadata…")
        self._set_action_state()
        worker.start()
        return True

    def _sync_instance_table(self) -> None:
        row = self.instance_model.row_for_comic(self.comic)
        if row < 0:
            return
        index = self.instance_model.index(row, 0)
        self.instance_table.selectionModel().blockSignals(True)
        try:
            self.instance_table.setCurrentIndex(index)
            self.instance_table.scrollTo(index)
        finally:
            self.instance_table.selectionModel().blockSignals(False)
    @staticmethod
    def _button(text, slot):
        button = QPushButton(text); button.clicked.connect(slot); return button

    def _digit_shortcut_may_fire(self) -> bool:
        if QApplication.activeModalWidget() is not None:
            return False
        fw = QApplication.focusWidget()
        if fw is None:
            return True
        return not isinstance(fw, (QLineEdit, QTextEdit))

    def _invoke_shortcut_action(self, button: QPushButton, slot) -> None:
        if not self._digit_shortcut_may_fire() or not button.isEnabled():
            return
        slot()

    def _install_digit_shortcuts(self) -> None:
        bindings = (
            (("1", Qt.Key.Key_1), self.search_button, self.search),
            (("2", Qt.Key.Key_2), self.apply_button, self.apply_proposal),
            (("3", Qt.Key.Key_3), self.discard_button, self.discard),
            (("4", Qt.Key.Key_4), self.save_button, self.save),
        )
        for num, button, slot in bindings:
            numpad_key, main_key = num
            for sequence in (QKeySequence(f"Num+{numpad_key}"), QKeySequence(main_key)):
                shortcut = QShortcut(sequence, self)
                shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
                shortcut.activated.connect(
                    lambda b=button, s=slot: self._invoke_shortcut_action(b, s)
                )
                self._digit_shortcuts.append(shortcut)

    def set_config(self, config=None, cache_enabled=None, *, api_key=None):
        if isinstance(config, str) or (config is None and api_key is not None):
            key = config if isinstance(config, str) else api_key
            config = type("MetadataConfig", (), {"api_key": key,
                "cache_enabled": True if cache_enabled is None else cache_enabled})()
        elif config is not None and cache_enabled is not None:
            setattr(config, "cache_enabled", bool(cache_enabled))
        self.config = config
    def set_comic(self, comic):
        if self.session and self.comic is comic:
            return True
        if self._write_worker is not None:
            if not self._has_pending_comic: self._pending_comic = comic; self._has_pending_comic = True
            self._set_status("Save in progress; selection will change when it finishes")
            return False
        if self.session and self.session.is_dirty:
            pending = len(self._dirty_sessions_queue())
            if pending > 1:
                message = (
                    f"This file and {pending - 1} other file(s) have unsaved changes. "
                    "Save or discard the current file before changing selection?"
                )
            else:
                message = (
                    "The current metadata draft has unsaved changes. "
                    "Save or discard it before changing selection?"
                )
            answer = QMessageBox.question(
                self, "Unsaved metadata", message,
                QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard |
                QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel)
            if answer in (QMessageBox.StandardButton.Save, QMessageBox.StandardButton.Yes):
                self._pending_comic = comic; self._has_pending_comic = True
                if not self.save(): self._pending_comic = None; self._has_pending_comic = False
                return False
            if answer not in (QMessageBox.StandardButton.Discard, QMessageBox.StandardButton.No):
                return False
        self._activate_comic(comic)
        return True

    def set_comics(self, comics):
        """Replace available local files while preserving the active path."""
        current_key = self._path_key
        self._available_comics = list(comics or [])
        valid_keys = {self._comic_path_key(comic) for comic in self._available_comics}
        self._extra_sessions = {
            key: session
            for key, session in self._extra_sessions.items()
            if key in valid_keys
        }
        self.comic_selector.blockSignals(True)
        try:
            self.comic_selector.clear()
            self.instance_model.set_comics(self._available_comics)
            self.instance_model.set_filter(self.instance_filter.text())
            for comic in self._available_comics:
                label = f"{comic.path.name} — {comic.series_name or comic.title or 'Unidentified'}"
                if comic.issue_number:
                    label += f" #{comic.issue_number}"
                item = QListWidgetItem(label)
                item.setData(Qt.ItemDataRole.UserRole, comic)
                self.comic_selector.addItem(item)
            for index in range(self.comic_selector.count()):
                if self._comic_path_key(self.comic_selector.item(index).data(Qt.ItemDataRole.UserRole)) == current_key:
                    self.comic_selector.setCurrentRow(index)
                    break
        finally:
            self.comic_selector.blockSignals(False)
        self._sync_instance_table()
        # A scan/enrichment may replace Comic objects without changing paths.
        # Rebind the session so subsequent edits target the current model object.
        if current_key and self.comic is not None:
            replacement = next((comic for comic in self._available_comics
                                if self._comic_path_key(comic) == current_key), None)
            if replacement is not None and replacement is not self.comic:
                self.set_comic(replacement)
        self._set_action_state()

    def _selector_changed(self, index):
        item = self.comic_selector.item(index) if index >= 0 else None
        comic = item.data(Qt.ItemDataRole.UserRole) if item else None
        if comic is not None and comic is not self.comic:
            if not self.set_comic(comic):
                self._sync_selector()
            else:
                logger.info("metadata_instance_selected path=%s", self._path_key)
                self.comic_focus_requested.emit(comic)

    def _sync_selector(self):
        self.comic_selector.blockSignals(True)
        try:
            for index in range(self.comic_selector.count()):
                if self._comic_path_key(self.comic_selector.item(index).data(Qt.ItemDataRole.UserRole)) == self._path_key:
                    self.comic_selector.setCurrentRow(index)
                    break
        finally:
            self.comic_selector.blockSignals(False)
        self._sync_instance_table()

    def _activate_comic(self, comic):
        self.shutdown_workers(); self._request_token += 1
        self.comic = comic
        key = self._comic_path_key(comic)
        if comic is not None and key in self._extra_sessions:
            self.session = self._extra_sessions[key]
        else:
            self.session = MetadataSession(comic) if comic is not None else None
        self._path_key = key; self._proposal = None
        self._changed_fields.clear(); self._pre_apply_values.clear()
        self._sync_selector()
        self._populate_form(); self._clear_candidates()
        self._clear_changed_highlights()
        self.instance_model.set_editing_path(self._path_key)
        self._set_status("Ready" if comic is not None else "No comic selected")
        self._refresh_working_set_context()
        self._set_action_state(); self._emit_dirty()
    set_current_comic = set_comic

    def _compute_changed_fields(self):
        """Determine which fields changed after applying a proposal."""
        current = self.session.values()
        self._changed_fields = {
            name for name in current
            if name in self._pre_apply_values and current[name] != self._pre_apply_values.get(name)
        }

    def _apply_changed_highlights(self):
        """Add visual highlighting to fields that changed during the last apply."""
        for name, widget in self.inputs.items():
            changed = name in self._changed_fields
            widget.setProperty(CHANGED_PROPERTY, changed)
            widget.style().unpolish(widget)
            widget.style().polish(widget)

    def _clear_changed_highlights(self):
        """Remove all changed-field highlights."""
        self._changed_fields.clear()
        for widget in self.inputs.values():
            widget.setProperty(CHANGED_PROPERTY, False)
            widget.style().unpolish(widget)
            widget.style().polish(widget)

    @property
    def is_dirty(self): return self._any_dirty()

    @property
    def proposal(self): return self._proposal

    @property
    def selected_proposal(self): return self._proposal

    @property
    def search_worker(self): return self._search_worker

    @property
    def write_worker(self): return self._write_worker
    def _populate_form(self):
        self._loading = True
        try:
            values = self.session.values() if self.session else {}
            for name, widget in self.inputs.items():
                value = values.get(name, "")
                value = join_web_links(value) if name == "web_links" else value
                if isinstance(widget, QTextEdit): widget.setPlainText(str(value or ""))
                else: widget.setText(str(value or ""))
        finally:
            self._loading = False
        draft = self.session.draft if self.session else None
        if draft is None: self.state_label.setText("No comic selected")
        else: self.state_label.setText(f"{draft.status} Comic Vine · {draft.cv_series_id or '—'} / {draft.cv_issue_id or '—'}")
    def _field_changed(self, name, value):
        if not self._loading and self.session and self._write_worker is None:
            self.session.set_field(name, value)
            if self.session.is_dirty and self._path_key:
                self._extra_sessions[self._path_key] = self.session
            self._emit_dirty(); self._set_action_state()
    def _emit_dirty(self):
        dirty = self._any_dirty()
        if getattr(self, "_last_dirty", None) != dirty:
            self._last_dirty = dirty; self.dirty_changed.emit(dirty)
        self._refresh_save_button_label()
    def _set_action_state(self):
        has_comic = self.session is not None
        searching = self._search_worker is not None
        busy = searching or self._hydrate_worker is not None or self._write_worker is not None
        selected = self._selected_comics()
        single_selection = len(selected) == 1
        multi_selection = len(selected) >= 2
        self.search_progress.setVisible(searching)
        if multi_selection:
            self.editor_stack.setCurrentWidget(self.batch_editor_page)
        else:
            self.editor_stack.setCurrentWidget(self.single_editor_page)
        self._sync_comicvine_panel_visibility(multi_selection)
        form_enabled = self._write_worker is None and not multi_selection
        for widget in self.inputs.values():
            widget.setEnabled(form_enabled)
        strip_enabled = self._write_worker is None and multi_selection
        for widget in self.batch_inputs.values():
            widget.setEnabled(strip_enabled)
        self.search_button.setEnabled(has_comic and not busy and single_selection)
        self.candidates_list.setEnabled(not searching)
        self.apply_button.setEnabled(self._proposal is not None and not busy)
        self.apply_to_selected_button.setEnabled(multi_selection and not busy)
        if multi_selection:
            self.apply_to_selected_button.setToolTip("")
        else:
            self.apply_to_selected_button.setToolTip("Select multiple files in the table")
        dirty = self._any_dirty()
        self.discard_button.setEnabled(has_comic and dirty and not busy)
        self.save_button.setEnabled(has_comic and dirty and not busy)
        self._refresh_save_button_label()
        self._refresh_working_set_context()
    def search(self): self._start_search()
    search_comic = search
    def _start_search(self):
        if not self.session or self._search_worker is not None or self._hydrate_worker is not None or self._write_worker is not None:
            return
        if len(self._selected_comics()) != 1:
            return
        from comicdesk.ui.api_key_prompt import ensure_api_key

        if not ensure_api_key(self, self.config, "Comic Vine search"):
            self._set_status("Comic Vine API key is required")
            return
        key = str(getattr(self.config, "api_key", "") or "").strip()
        self._request_token += 1; token, path = self._request_token, self._path_key
        self._proposal = None
        self._stop_cover_loaders()
        self._clear_candidates()
        self._search_worker = MetadataSearchWorker(self.session.snapshot(), key, cache_enabled=bool(getattr(self.config, "cache_enabled", True)), token=token)
        worker = self._search_worker
        worker.finished.connect(lambda result, w=worker, t=token, p=path: self._search_finished(result, w, t, p))
        worker.error.connect(lambda message, w=worker, t=token, p=path: self._search_error(message, w, t, p))
        self._set_status("Searching Comic Vine…"); self._set_action_state(); worker.start()
    def _search_finished(self, result, worker, token, path):
        if worker is not self._search_worker or token != self._request_token or path != self._path_key:
            self._release_worker(worker)
            return
        self._search_worker = None
        self._release_worker(worker)
        candidates = list(getattr(result, "issues", []) or [])
        if not candidates and getattr(result, "issue", None) is not None: candidates = [result.issue]
        self._show_candidates(candidates); status = getattr(result, "status", "")
        if status == STATUS_EMPTY or not candidates: self._set_status("No Comic Vine results")
        elif status == STATUS_CANDIDATES: self._set_status("Select a proposal before applying it")
        else: self._set_status("Exact proposal selected; apply it explicitly"); self.candidates_list.setCurrentRow(0)
        self._set_action_state()
    def _search_error(self, message, worker, token, path):
        if worker is not self._search_worker or token != self._request_token or path != self._path_key:
            self._release_worker(worker)
            return
        self._search_worker = None
        self._release_worker(worker)
        self._set_status(message)
        self._set_action_state()
    def _show_candidates(self, candidates):
        self._stop_cover_loaders()
        self.candidates_list.clear()
        count = len(candidates)
        if count:
            self.proposals_label.setText(
                f"Proposals — {count} result{'s' if count != 1 else ''}"
            )
        else:
            self.proposals_label.setText("Proposals")
        for row, candidate in enumerate(candidates):
            headline, subtitle, detail = candidate_lines(candidate)
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, candidate)
            item.setSizeHint(QSize(0, CANDIDATE_ROW_HEIGHT))
            row_widget = CandidateResultRow(headline, subtitle, detail, self._theme)
            self.candidates_list.addItem(item)
            self.candidates_list.setItemWidget(item, row_widget)
            image_url = getattr(candidate, "image_url", "") or ""
            if image_url:
                loader = CoverLoader(image_url, row)
                loader.finished.connect(
                    lambda data, r, w=loader: self._on_cover_loaded(data, r, w)
                )
                loader.error.connect(lambda r, w=loader: self._on_cover_error(r, w))
                self._cover_loaders.append(loader)
                loader.start()
        self.candidates_list.clearSelection()
        self.candidates_list.setCurrentRow(-1)

    def _on_cover_loaded(self, data: bytes, row: int, worker: CoverLoader) -> None:
        if worker in self._cover_loaders:
            self._cover_loaders.remove(worker)
        worker.deleteLater()
        if row < 0 or row >= self.candidates_list.count():
            return
        item = self.candidates_list.item(row)
        widget = self.candidates_list.itemWidget(item)
        if not isinstance(widget, CandidateResultRow):
            return
        pixmap = QPixmap()
        if pixmap.loadFromData(data):
            widget.set_cover_pixmap(pixmap)

    def _on_cover_error(self, row: int, worker: CoverLoader) -> None:
        if worker in self._cover_loaders:
            self._cover_loaders.remove(worker)
        worker.deleteLater()
        if row < 0 or row >= self.candidates_list.count():
            return
        item = self.candidates_list.item(row)
        widget = self.candidates_list.itemWidget(item)
        if isinstance(widget, CandidateResultRow):
            widget.set_cover_failed()

    def _release_cover_loader(self, loader: CoverLoader) -> None:
        if loader in self._cover_loaders:
            self._cover_loaders.remove(loader)
        loader.cancel()
        try:
            loader.finished.disconnect()
        except (TypeError, RuntimeError):
            pass
        try:
            loader.error.disconnect()
        except (TypeError, RuntimeError):
            pass
        self._join_or_defer_delete(
            loader, defer_signals=(loader.finished, loader.error)
        )

    def _stop_cover_loaders(self) -> None:
        for loader in list(self._cover_loaders):
            self._release_cover_loader(loader)
        self._cover_loaders.clear()
    def _candidate_selected(self):
        item = self.candidates_list.currentItem()
        candidate = item.data(Qt.ItemDataRole.UserRole) if item else None
        self._proposal = candidate if self._is_proposal(candidate) else None
        self._set_action_state()
        if self._proposal is not None and self._is_issue(self._proposal):
            if issue_needs_hydrate(self._proposal) or issue_needs_volume_resolve(self._proposal):
                self._hydrate_candidate(self._proposal)
    @staticmethod
    def _is_issue(candidate):
        return candidate is not None and hasattr(candidate, "issue_number") and hasattr(candidate, "series_id")

    @staticmethod
    def _is_proposal(candidate):
        return CbzMetadataPanel._is_issue(candidate) or isinstance(candidate, ComicVineVolume)

    def _hydrate_candidate(self, candidate):
        """Fetch complete Comic Vine details for a selected candidate."""
        self._stop_hydrate_worker()
        key = str(getattr(self.config, "api_key", "") or "").strip()
        if not key or not getattr(candidate, "id", None):
            return
        self._request_token += 1
        token, path = self._request_token, self._path_key
        self._hydrate_worker = MetadataHydrateWorker(
            candidate, key,
            cache_enabled=bool(getattr(self.config, "cache_enabled", True)),
            token=token,
        )
        worker = self._hydrate_worker
        worker.finished.connect(lambda hydrated, w=worker, t=token, p=path: self._hydrate_finished(hydrated, w, t, p))
        worker.error.connect(lambda msg, w=worker, t=token, p=path: self._hydrate_error(msg, w, t, p))
        self._set_status("Loading complete Comic Vine metadata…")
        self._set_action_state()
        worker.start()

    def _hydrate_finished(self, hydrated, worker, token, path):
        if worker is not self._hydrate_worker or token != self._request_token or path != self._path_key:
            self._release_worker(worker)
            return
        self._hydrate_worker = None
        self._release_worker(worker)
        self._proposal = hydrated
        self._set_status("Complete metadata loaded; apply it to the draft")
        self._set_action_state()

    def _hydrate_error(self, message, worker, token, path):
        if worker is not self._hydrate_worker or token != self._request_token or path != self._path_key:
            self._release_worker(worker)
            return
        self._hydrate_worker = None
        self._release_worker(worker)
        self._set_status(f"Hydration failed: {message}")
        self._set_action_state()
    def apply_proposal(self):
        if not self.session or self._proposal is None or self._write_worker is not None: return
        self._pre_apply_values = self.session.values()
        self.session.apply_proposal(self._proposal, overwrite=True)
        self._populate_form()
        self._compute_changed_fields()
        self._apply_changed_highlights()
        logger.info("metadata_proposal_applied comic_path=%s volume=%s series_id=%s dirty=%s",
                    self._path_key, self.session.draft.volume,
                    self.session.draft.cv_series_id, self.session.is_dirty)
        self._set_status("Proposal applied to draft; save to persist it")
        if self.session.is_dirty and self._path_key:
            self._extra_sessions[self._path_key] = self.session
        self._emit_dirty(); self._set_action_state()
    apply_selected_proposal = apply_proposal
    def discard(self):
        if not self.session or self._write_worker is not None:
            return
        pending = len(self._dirty_sessions_queue())
        if pending > 1:
            answer = QMessageBox.question(
                self,
                "Discard draft",
                f"Discard unsaved changes for {pending} files?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        for session in list(self._extra_sessions.values()):
            session.discard()
        self._extra_sessions.clear()
        self.session.discard(); self._proposal = None; self._populate_form(); self._clear_candidates()
        self._clear_changed_highlights()
        self._set_status("Draft discarded")
        self._refresh_working_set_context()
        self._emit_dirty(); self._set_action_state()
    discard_changes = discard
    def save(self):
        if self._write_worker is not None:
            return False
        queue = self._dirty_sessions_queue()
        if not queue:
            return False
        self._write_queue = queue
        self._write_queue_total = len(queue)
        self._write_queue_succeeded = 0
        self._write_queue_failed = 0
        return self._start_next_write()
    save_metadata = save
    def _write_finished(self, saved, worker, token, path):
        if worker is not self._write_worker:
            self._release_worker(worker)
            return
        session = self._write_session or self.session
        self._write_worker = None; self._write_completion = None
        self._release_worker(worker)
        saved_path = Path(saved)
        if session is not None:
            session.draft.path = saved_path
        saved_comic = session.mark_saved() if session is not None else self.comic
        saved_key = self._comic_path_key(saved_comic)
        if saved_key in self._extra_sessions and self._extra_sessions[saved_key] is session:
            del self._extra_sessions[saved_key]
        self._write_queue_succeeded += 1
        if self._write_queue and self._write_queue[0] is session:
            self._write_queue.pop(0)
        self.instance_model.notify_comic_changed(saved_comic)
        if session is self.session:
            self._path_key = saved_key
            self.instance_model.set_editing_path(self._path_key)
            self._populate_form()
            self._clear_changed_highlights()
        self.metadata_saved.emit(saved_comic, path)
        if self._write_queue:
            self._write_session = None
            self._start_next_write()
            return
        self._write_session = None
        total = self._write_queue_total
        if total > 1:
            self._set_status(f"Metadata saved to {self._write_queue_succeeded} archive(s)")
        elif session is self.session:
            self._set_status(f"Metadata saved to {saved}")
        self._emit_dirty(); self._set_action_state()
        self._refresh_working_set_context()
        if self._has_pending_comic:
            pending = self._pending_comic; self._pending_comic = None; self._has_pending_comic = False
            self._activate_comic(pending)
    def _write_error(self, message, worker, token, path):
        if worker is not self._write_worker:
            self._release_worker(worker)
            return
        succeeded = self._write_queue_succeeded
        self._write_worker = None; self._write_session = None; self._write_completion = None
        self._write_queue.clear()
        self._write_queue_total = 0
        self._release_worker(worker)
        self._pending_comic = None; self._has_pending_comic = False
        if succeeded:
            self._set_status(
                f"Save failed after {succeeded} succeeded: {message}"
            )
        else:
            self._set_status(message)
        self._emit_dirty(); self._set_action_state()
    def _record_write_completion(self, worker, success, value):
        if worker is self._write_worker: self._write_completion = (success, value)
    def _clear_candidates(self):
        self._stop_cover_loaders()
        self.candidates_list.clear()
        self.proposals_label.setText("Proposals")
    def _set_status(self, message): self.status_label.setText(message); self.status_message.emit(message)
    @staticmethod
    def _comic_path_key(comic):
        raw_path = getattr(comic, "path", None) if comic is not None else None
        return str(Path(raw_path)) if raw_path else ""

    def notify_comic_renamed(self, comic: Comic) -> None:
        """Keep the active metadata session aligned after a library file rename."""
        if comic is None or self.comic is not comic:
            return
        self._path_key = self._comic_path_key(comic)
        self.instance_model.set_editing_path(self._path_key)
    def _join_or_defer_delete(self, thread, *, defer_signals=None) -> None:
        if thread.isRunning():
            if not thread.wait(WORKER_JOIN_TIMEOUT_MS):
                signals = defer_signals if defer_signals is not None else (thread.finished,)
                for signal in signals:
                    signal.connect(thread.deleteLater)
                return
        thread.deleteLater()

    def _release_worker(self, worker) -> None:
        """Stop a metadata worker and destroy it only after the thread exits."""
        if worker is None:
            return
        worker.cancel()
        self._join_or_defer_delete(worker)

    def _stop_search_worker(self) -> None:
        worker = self._search_worker
        if worker is None:
            return
        self._search_worker = None
        self._release_worker(worker)

    def _stop_hydrate_worker(self) -> None:
        worker = self._hydrate_worker
        if worker is None:
            return
        self._hydrate_worker = None
        self._release_worker(worker)

    def shutdown_workers(self):
        self._stop_cover_loaders()
        self._stop_search_worker()
        self._stop_hydrate_worker()
        self._wait_for_write()
        self._request_token += 1
        self._set_action_state()
    def _wait_for_write(self):
        worker = self._write_worker
        if worker is None: return
        if worker.isRunning(): worker.wait()
        QCoreApplication.processEvents()
        if self._write_worker is not worker: return
        completion = self._write_completion
        if completion is None: return
        success, value = completion
        handler = self._write_finished if success else self._write_error
        handler(value, worker, worker.token, self._path_key)
    close_workers = shutdown_workers
    def closeEvent(self, event):
        self.shutdown_workers(); super().closeEvent(event)
CBZMetadataPanel = CbzMetadataPanel
MetadataPanel = CbzMetadataPanel
