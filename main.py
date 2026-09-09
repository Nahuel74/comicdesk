"""Entry point for ComicDesk application."""

import sys
import logging

# Configure logging - only show warnings and errors
logging.basicConfig(
    level=logging.WARNING,
    format="%(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

# Enable debug only for our app
logging.getLogger("comicdesk").setLevel(logging.INFO)

from comicdesk.app import run


if __name__ == "__main__":
    sys.exit(run())
