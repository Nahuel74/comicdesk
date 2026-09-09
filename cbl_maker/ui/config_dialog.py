"""Configuration dialog."""

from PySide6.QtWidgets import (
    QComboBox, QDialog, QVBoxLayout, QFormLayout, QLineEdit,
    QPushButton, QHBoxLayout, QCheckBox, QFileDialog,
    QMessageBox, QLabel, QWidget
)
from PySide6.QtCore import QThread, Signal

from cbl_maker.config import Config, normalize_theme
from cbl_maker.services.comicvine_api import ComicVineClient
from cbl_maker.ui.theme import button_stylesheet, colors_for, dialog_stylesheet


class ValidateApiKeyWorker(QThread):
    """Worker thread for API key validation."""
    finished = Signal(bool)
    error = Signal(str)

    def __init__(self, api_key):
        super().__init__()
        self.api_key = api_key

    def run(self):
        try:
            client = ComicVineClient(self.api_key, cache_enabled=False)
            result = client.validate_api_key()
            self.finished.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))


class ConfigDialog(QDialog):
    """Configuration dialog for API key and settings."""

    def __init__(self, config: Config, parent=None):
        super().__init__(parent)
        self.config = config
        self._theme = normalize_theme(config.theme)
        self._setup_ui()

    def _setup_ui(self):
        """Set up the dialog UI."""
        self.setWindowTitle("Settings")
        self.setMinimumWidth(450)

        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        self.title_label = QLabel("Settings")
        layout.addWidget(self.title_label)

        form = QFormLayout()
        form.setSpacing(12)

        theme_label = QLabel("Theme:")
        self.theme_combo = QComboBox()
        self.theme_combo.addItem("Dark", "dark")
        self.theme_combo.addItem("Light", "light")
        theme_index = self.theme_combo.findData(normalize_theme(self.config.theme))
        if theme_index >= 0:
            self.theme_combo.setCurrentIndex(theme_index)
        form.addRow(theme_label, self.theme_combo)

        api_key_label = QLabel("Comic Vine API Key:")
        self.api_key_input = QLineEdit(self.config.api_key)
        self.api_key_input.setEchoMode(QLineEdit.Password)
        self.api_key_input.setPlaceholderText("Enter your API key...")
        form.addRow(api_key_label, self.api_key_input)

        validate_layout = QHBoxLayout()
        self.validate_btn = QPushButton("Validate Key")
        self.validate_btn.clicked.connect(self._validate_key)
        validate_layout.addWidget(self.validate_btn)
        validate_layout.addStretch()
        form.addRow("", validate_layout)

        folder_label = QLabel("Default Folder:")
        folder_layout = QHBoxLayout()
        self.folder_input = QLineEdit(self.config.default_folder)
        self.folder_input.setPlaceholderText("Select default folder...")
        self.folder_btn = QPushButton("Browse...")
        self.folder_btn.clicked.connect(self._browse_folder)
        folder_layout.addWidget(self.folder_input)
        folder_layout.addWidget(self.folder_btn)
        form.addRow(folder_label, folder_layout)

        self.cache_checkbox = QCheckBox("Enable API cache")
        self.cache_checkbox.setChecked(self.config.cache_enabled)
        form.addRow("", self.cache_checkbox)

        getcomics_folder_label = QLabel("GetComics download folder:")
        getcomics_folder_layout = QHBoxLayout()
        self.getcomics_folder_input = QLineEdit(
            getattr(self.config, "getcomics_download_folder", "") or self.config.default_folder
        )
        self.getcomics_folder_input.setPlaceholderText("Defaults to default folder when empty...")
        self.getcomics_folder_btn = QPushButton("Browse...")
        self.getcomics_folder_btn.clicked.connect(self._browse_getcomics_folder)
        getcomics_folder_layout.addWidget(self.getcomics_folder_input)
        getcomics_folder_layout.addWidget(self.getcomics_folder_btn)
        form.addRow(getcomics_folder_label, getcomics_folder_layout)

        self.auto_enrich_checkbox = QCheckBox("Auto-enrich GetComics downloads from Comic Vine")
        self.auto_enrich_checkbox.setChecked(
            getattr(self.config, "auto_enrich_after_download", True)
        )
        form.addRow("", self.auto_enrich_checkbox)

        layout.addLayout(form)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)

        self.save_btn = QPushButton("Save")
        self.save_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self.save_btn)

        layout.addLayout(btn_layout)
        self.apply_theme(self._theme)

    def apply_theme(self, theme: str) -> None:
        """Re-apply visual tokens for the active theme."""
        self._theme = normalize_theme(theme)
        c = colors_for(self._theme)
        self.setStyleSheet(dialog_stylesheet(self._theme))
        self.title_label.setStyleSheet(
            f"font-size: 18px; font-weight: bold; color: {c['text']};"
        )
        default_btn = button_stylesheet(self._theme, "default")
        for button in (
            self.validate_btn,
            self.folder_btn,
            self.getcomics_folder_btn,
            self.cancel_btn,
        ):
            button.setStyleSheet(default_btn)
        self.save_btn.setStyleSheet(button_stylesheet(self._theme, "primary"))

    def _validate_key(self):
        """Validate the API key."""
        api_key = self.api_key_input.text().strip()
        if not api_key:
            QMessageBox.warning(self, "Error", "Please enter an API key")
            return

        self.validate_btn.setEnabled(False)
        self.validate_btn.setText("Validating...")

        self.worker = ValidateApiKeyWorker(api_key)
        self.worker.finished.connect(self._on_validation_result)
        self.worker.error.connect(self._on_validation_error)
        self.worker.start()

    def _on_validation_result(self, valid):
        """Handle validation result."""
        self.validate_btn.setEnabled(True)
        self.validate_btn.setText("Validate Key")

        if valid:
            QMessageBox.information(self, "Success", "API key is valid!")
        else:
            QMessageBox.warning(self, "Error", "Invalid API key")

    def _on_validation_error(self, message):
        self.validate_btn.setEnabled(True)
        self.validate_btn.setText("Validate Key")
        QMessageBox.warning(self, "Comic Vine error", message)

    def _browse_folder(self):
        """Browse for default folder."""
        folder = QFileDialog.getExistingDirectory(
            self, "Select Default Folder", self.folder_input.text()
        )
        if folder:
            self.folder_input.setText(folder)

    def _browse_getcomics_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select GetComics Download Folder", self.getcomics_folder_input.text()
        )
        if folder:
            self.getcomics_folder_input.setText(folder)

    def get_config(self) -> Config:
        """Get the updated configuration."""
        return Config(
            api_key=self.api_key_input.text().strip(),
            default_folder=self.folder_input.text().strip(),
            cache_enabled=self.cache_checkbox.isChecked(),
            last_cbl_directory=self.config.last_cbl_directory,
            getcomics_download_folder=self.getcomics_folder_input.text().strip(),
            auto_enrich_after_download=self.auto_enrich_checkbox.isChecked(),
            theme=normalize_theme(self.theme_combo.currentData()),
        )
