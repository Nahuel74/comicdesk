"""Application setup and main entry point."""

import sys
from PySide6.QtWidgets import QApplication
from cbl_maker.ui.main_window import MainWindow


def run() -> int:
    """Run the application."""
    app = QApplication(sys.argv)
    app.setApplicationName("CBL Maker")
    app.setOrganizationName("CBLMaker")
    app.setStyle("Fusion")

    window = MainWindow()
    window.show()
    
    return app.exec()
