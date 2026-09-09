"""Application setup and main entry point."""

import sys
from PySide6.QtWidgets import QApplication
from comicdesk.ui.main_window import MainWindow


def run() -> int:
    """Run the application."""
    app = QApplication(sys.argv)
    app.setApplicationName("ComicDesk")
    app.setOrganizationName("ComicDesk")
    app.setStyle("Fusion")

    window = MainWindow()
    window.show()
    
    return app.exec()
