"""Startup phase logging shared by the entry point and main window."""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager

logger = logging.getLogger("comicdesk.startup")


@contextmanager
def startup_phase(name: str):
    """Log begin/end of a startup step and elapsed milliseconds."""
    logger.info("→ %s …", name)
    started = time.perf_counter()
    try:
        yield
    except Exception:
        elapsed_ms = (time.perf_counter() - started) * 1000
        logger.exception("✗ %s failed after %.0f ms", name, elapsed_ms)
        raise
    elapsed_ms = (time.perf_counter() - started) * 1000
    logger.info("✓ %s (%.0f ms)", name, elapsed_ms)
