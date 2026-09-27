"""Perceptual cover hashing to disambiguate Comic Vine candidates."""

from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Iterable

import httpx

logger = logging.getLogger(__name__)

try:
    from PIL import Image
    import imagehash
except ImportError:  # pragma: no cover - optional at import time
    Image = None  # type: ignore
    imagehash = None  # type: ignore


def cover_hash_available() -> bool:
    return Image is not None and imagehash is not None


def hash_archive_cover(archive_path: Path) -> str | None:
    """Return hex phash of the first image member in a CBZ/CBR, or None."""
    if not cover_hash_available():
        return None
    from comicdesk.services.comic_archive import read_first_image_bytes

    try:
        data = read_first_image_bytes(archive_path)
    except Exception as exc:
        logger.debug("Cover hash skipped for %s: %s", archive_path, exc)
        return None
    if not data:
        return None
    try:
        image = Image.open(io.BytesIO(data))
        return str(imagehash.phash(image))
    except Exception as exc:
        logger.debug("Cover hash failed for %s: %s", archive_path, exc)
        return None


def hash_image_url(url: str, client: httpx.Client | None = None) -> str | None:
    if not cover_hash_available() or not url:
        return None
    own_client = client is None
    http = client or httpx.Client(timeout=20.0, follow_redirects=True)
    try:
        response = http.get(url)
        response.raise_for_status()
        image = Image.open(io.BytesIO(response.content))
        return str(imagehash.phash(image))
    except Exception as exc:
        logger.debug("Remote cover hash failed: %s", exc)
        return None
    finally:
        if own_client:
            http.close()


def pick_closest_cover_candidate(
    archive_path: Path,
    candidates: Iterable,
    *,
    image_url_attr: str = "image_url",
    client: httpx.Client | None = None,
):
    """Return the candidate whose cover hash is closest to the archive, if any."""
    if not cover_hash_available():
        return None
    local_hash = hash_archive_cover(archive_path)
    if not local_hash:
        return None
    local = imagehash.hex_to_hash(local_hash)
    best = None
    best_distance = None
    own_client = client is None
    http = client or httpx.Client(timeout=20.0, follow_redirects=True)
    try:
        for candidate in candidates:
            url = str(getattr(candidate, image_url_attr, "") or "").strip()
            remote_hex = hash_image_url(url, http)
            if not remote_hex:
                continue
            distance = local - imagehash.hex_to_hash(remote_hex)
            if best_distance is None or distance < best_distance:
                best_distance = distance
                best = candidate
    finally:
        if own_client:
            http.close()
    if best_distance is not None and best_distance <= 12:
        return best
    return None
