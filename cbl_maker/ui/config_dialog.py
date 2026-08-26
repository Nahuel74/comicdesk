"""Configuration dialog."""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLineEdit,
    QPushButton, QHBoxLayout, QCheckBox, QFileDialog,
    QMessageBox
)
from PySide6.QtCore import QThread, Signal

from cbl_maker.config import Config
from cbl_maker.services.comicvine_api import ComicVineClient


class ValidateApiKeyWorker(QThread):
    """Worker thread for API key validation."""
    finished = Signal(bool)

    def __init__(self, api_key):
        super().__init__()
        self.api_key = api_key

    def run(self):
        client = ComicVineClient(self.api_key, cache_enabled=False)
        result = client.validate_api_key()
        self.finished.emit(result)


class ConfigDialog(QDialog):
    """Configuration dialog for API key and settings."""

    def __init__(self, config: Config, parent=None):
        super().__init__(parent)
        self.config = config
        self._setup_ui()

    def _setup_ui(self):
        """Set up the dialog UI."""
        self.setWindowTitle("Settings")
        self.setMinimumWidth(400)
        
        layout = QVBoxLayout(self)
        form = QFormLayout()
        
        # API Key
        self.api_key_input = QLineEdit(self.config.api_key)
        self.api_key_input.setEchoMode(QLineEdit.Password)
        form.addRow("Comic Vine API Key:", self.api_key_input)
        
        # Validate button
        self.validate_btn = QPushButton("Validate Key")
        self.validate_btn.clicked.connect(self._validate_key)
        form.addRow("", self.validate_btn)
        
        # Default folder
        folder_layout = QHBoxLayout()
        self.folder_input = QLineEdit(self.config.default_folder)
        folder_btn = QPushButton("Browse...")
        folder_btn.clicked.connect(self._browse_folder)
        folder_layout.addWidget(self.folder_input)
        folder_layout.addWidget(folder_btn)
        form.addRow("Default Folder:", folder_layout)
        
        # Cache enabled
        self.cache_checkbox = QCheckBox("Enable API cache")
        self.cache_checkbox.setChecked(self.config.cache_enabled)
        form.addRow("", self.cache_checkbox)
        
        layout.addLayout(form)
        
        # Buttons
        btn_layout = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)
        
        layout.addLayout(btn_layout)

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
        self.worker.start()

    def _on_validation_result(self, valid):
        """Handle validation result."""
        self.validate_btn.setEnabled(True)
        self.validate_btn.setText("Validate Key")
        
        if valid:
            QMessageBox.information(self, "Success", "API key is valid!")
        else:
            QMessageBox.warning(self, "Error", "Invalid API key")

    def _browse_folder(self):
        """Browse for default folder."""
        folder = QFileDialog.getExistingDirectory(
            self, "Select Default Folder", self.folder_input.text()
        )
        if folder:
            self.folder_input.setText(folder)

    def get_config(self) -> Config:
        """Get the updated configuration."""
        return Config(
            api_key=self.api_key_input.text().strip(),
            default_folder=self.folder_input.text().strip(),
            cache_enabled=self.cache_checkbox.isChecked()
        )
