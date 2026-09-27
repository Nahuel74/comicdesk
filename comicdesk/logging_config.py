"""Central logging setup for ComicDesk."""

from __future__ import annotations

import logging
import os
import sys


def configure_logging() -> None:
    """Configure root and comicdesk loggers (call once from main.py)."""
    level_name = os.environ.get("COMICDESK_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
        force=True,
    )
    logging.getLogger("comicdesk").setLevel(level)
    # Qt can be noisy at INFO; keep our startup lines visible.
    logging.getLogger("comicdesk.startup").setLevel(level)
