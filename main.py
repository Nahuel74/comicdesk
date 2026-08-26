"""Entry point for CBL Maker application."""

import sys
import logging

# Configure logging - only show warnings and errors
logging.basicConfig(
    level=logging.WARNING,
    format="%(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

# Enable debug only for our app
logging.getLogger("cbl_maker").setLevel(logging.INFO)

from cbl_maker.app import run


if __name__ == "__main__":
    sys.exit(run())
