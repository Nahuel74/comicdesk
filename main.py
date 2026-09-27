"""Entry point for ComicDesk application."""

import sys

from comicdesk.logging_config import configure_logging

configure_logging()

from comicdesk.app import run


if __name__ == "__main__":
    sys.exit(run())
