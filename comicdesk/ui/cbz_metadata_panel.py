"""Themed editor for metadata belonging to one selected comic archive."""
from __future__ import annotations
from pathlib import Path
import logging
from PySide6.QtCore import QCoreApplication, QSize, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
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
from comicdesk.services.metadata_session import MetadataSession
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

        working_set = QGroupBox("Working set — select a comic from the scanned folder")
        working_layout = QVBoxLayout(working_set)
        filter_row = QHBoxLayout()
        self.instance_filter = QLineEdit()
        self.instance_filter.setPlaceholderText("Filter files in folder…")
        self.instance_filter.textChanged.connect(self._on_instance_filter_changed)
        filter_row.addWidget(self.instance_filter, 1)
        working_layout.addLayout(filter_row)

        self.instance_model = MetadataInstanceModel(self)
        self.instance_table = QTableView()
        self.instance_table.setModel(self.instance_model)
        self.instance_table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.instance_table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.instance_table.verticalHeader().setVisible(False)
        header = self.instance_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in (1, 2, 3):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self.instance_table.setMinimumHeight(140)
        self.instance_table.setMaximumHeight(180)
        self.instance_table.selectionModel().currentRowChanged.connect(self._on_instance_row_changed)
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
        editor_layout.addWidget(self.scroll, 1)
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
        self.discard_button = self._button("Discard draft", self.discard)
        self.discard_btn = self.discard_button
        self.save_button = self._button("3. Save to archive", self.save)
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
        body_splitter.addWidget(cv_panel)
        body_splitter.setStretchFactor(0, 3)
        body_splitter.setStretchFactor(1, 1)
        body_splitter.setSizes([700, 340])
        outer.addWidget(body_splitter, 1)
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
        default_btn = button_stylesheet(theme, "default")
        for button in (
            self.search_button,
            self.apply_button,
            self.discard_button,
        ):
            button.setStyleSheet(default_btn)
        self.save_button.setStyleSheet(button_stylesheet(theme, "primary"))
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

    def _on_instance_row_changed(self, current, _previous) -> None:
        if current.isValid():
            self._selector_changed(current.row())

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
            answer = QMessageBox.question(
                self, "Unsaved metadata",
                "The current metadata draft has unsaved changes. Save or discard it before changing selection?",
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
        self.comic = comic; self.session = MetadataSession(comic) if comic is not None else None
        self._path_key = self._comic_path_key(comic); self._proposal = None
        self._changed_fields.clear(); self._pre_apply_values.clear()
        self._sync_selector()
        self._populate_form(); self._clear_candidates()
        self._clear_changed_highlights()
        self._set_status("Ready" if comic is not None else "No comic selected")
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
    def is_dirty(self): return bool(self.session and self.session.is_dirty)

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
            self.session.set_field(name, value); self._emit_dirty(); self._set_action_state()
    def _emit_dirty(self):
        dirty = bool(self.session and self.session.is_dirty)
        if getattr(self, "_last_dirty", None) != dirty:
            self._last_dirty = dirty; self.dirty_changed.emit(dirty)
    def _set_action_state(self):
        has_comic = self.session is not None
        searching = self._search_worker is not None
        busy = searching or self._hydrate_worker is not None or self._write_worker is not None
        self.search_progress.setVisible(searching)
        for widget in self.inputs.values(): widget.setEnabled(self._write_worker is None)
        self.search_button.setEnabled(has_comic and not busy)
        self.candidates_list.setEnabled(not searching)
        self.apply_button.setEnabled(self._proposal is not None and not busy)
        dirty = bool(self.session and self.session.is_dirty)
        self.discard_button.setEnabled(has_comic and dirty and not busy); self.save_button.setEnabled(has_comic and dirty and not busy)
    def search(self): self._start_search()
    search_comic = search
    def _start_search(self):
        if not self.session or self._search_worker is not None or self._hydrate_worker is not None or self._write_worker is not None: return
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
        candidates = list(getattr(result, "issues", []) or []) or list(getattr(result, "volumes", []) or [])
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

    def _stop_cover_loaders(self) -> None:
        for loader in self._cover_loaders:
            loader.cancel()
            if loader.isRunning():
                loader.wait(100)
            loader.deleteLater()
        self._cover_loaders.clear()
    def _candidate_selected(self):
        item = self.candidates_list.currentItem()
        candidate = item.data(Qt.ItemDataRole.UserRole) if item else None
        self._proposal = candidate if self._is_proposal(candidate) else None
        self._set_action_state()
        if self._proposal is not None and self._is_issue(self._proposal):
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
        self._emit_dirty(); self._set_action_state()
    apply_selected_proposal = apply_proposal
    def discard(self):
        if not self.session or self._write_worker is not None: return
        self.session.discard(); self._proposal = None; self._populate_form(); self._clear_candidates()
        self._clear_changed_highlights()
        self._set_status("Draft discarded"); self._emit_dirty(); self._set_action_state()
    discard_changes = discard
    def save(self):
        if not self.session or not self.session.is_dirty or self._write_worker is not None: return False
        raw_path = self.session.draft.path
        if not raw_path or str(raw_path) == ".":
            self._set_status("Cannot save metadata: no local comic file path is available"); return False
        self._request_token += 1; token, path_key = self._request_token, self._path_key
        self._write_session = self.session; self._write_completion = None
        self._write_worker = MetadataWriteWorker(self.session.snapshot(), token=token, path=Path(raw_path))
        worker = self._write_worker
        worker.finished.connect(lambda saved, w=worker, t=token, p=path_key: self._write_finished(saved, w, t, p))
        worker.error.connect(lambda message, w=worker, t=token, p=path_key: self._write_error(message, w, t, p))
        recorder = lambda value, w=worker: self._record_write_completion(w, True, value)
        error_recorder = lambda message, w=worker: self._record_write_completion(w, False, message)
        try:
            worker.finished.connect(recorder, Qt.ConnectionType.DirectConnection)
            worker.error.connect(error_recorder, Qt.ConnectionType.DirectConnection)
        except TypeError:  # Lightweight test doubles may only accept one argument.
            pass
        self._set_status("Saving metadata…"); self._set_action_state(); worker.start()
        return True
    save_metadata = save
    def _write_finished(self, saved, worker, token, path):
        if worker is not self._write_worker:
            self._release_worker(worker)
            return
        session = self._write_session or self.session
        self._write_worker = None; self._write_session = None; self._write_completion = None
        self._release_worker(worker)
        saved_path = Path(saved)
        if session is not None:
            session.draft.path = saved_path
        saved_comic = session.mark_saved() if session is not None else self.comic
        self._path_key = self._comic_path_key(saved_comic)
        if session is self.session:
            self._populate_form()
            self._clear_changed_highlights()
            self._set_status(f"Metadata saved to {saved}"); self._emit_dirty(); self._set_action_state()
            self.metadata_saved.emit(saved_comic, path)
        if self._has_pending_comic:
            pending = self._pending_comic; self._pending_comic = None; self._has_pending_comic = False
            self._activate_comic(pending)
    def _write_error(self, message, worker, token, path):
        if worker is not self._write_worker:
            self._release_worker(worker)
            return
        self._write_worker = None; self._write_session = None; self._write_completion = None
        self._release_worker(worker)
        self._pending_comic = None; self._has_pending_comic = False
        self._set_status(message); self._set_action_state()
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
    def _release_worker(self, worker) -> None:
        """Stop a metadata worker and destroy it only after the thread exits."""
        if worker is None:
            return
        worker.cancel()
        if worker.isRunning():
            if not worker.wait(WORKER_JOIN_TIMEOUT_MS):
                worker.finished.connect(worker.deleteLater)
                return
        worker.deleteLater()

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
