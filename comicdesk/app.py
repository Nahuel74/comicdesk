"""Application setup and main entry point."""

import logging
import sys

from PySide6.QtWidgets import QApplication

from comicdesk.startup_trace import startup_phase
from comicdesk.ui.main_window import MainWindow

logger = logging.getLogger("comicdesk.startup")


def run() -> int:
    """Run the application."""
    with startup_phase("Qt application"):
        app = QApplication(sys.argv)
        app.setApplicationName("ComicDesk")
        app.setOrganizationName("ComicDesk")
        app.setStyle("Fusion")

    logger.info("Building main window (UI may appear before this finishes)…")
    window = MainWindow()
    logger.info("Entering Qt event loop")
    return app.exec()
