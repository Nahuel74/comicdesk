"""Configuration management for ComicDesk."""

import json
import logging
import os
import shutil
import tempfile
from pathlib import Path
from dataclasses import asdict, dataclass, fields

logger = logging.getLogger(__name__)

OLD_CONFIG_DIR = Path.home() / ".config" / "cbl-maker"
CONFIG_DIR = Path.home() / ".config" / "comicdesk"
CONFIG_FILE = CONFIG_DIR / "config.json"


def _migrate_legacy_config() -> None:
    """Copy legacy CBL Maker config into the ComicDesk directory on first run."""
    if CONFIG_DIR.exists() or not OLD_CONFIG_DIR.exists():
        return
    try:
        shutil.copytree(OLD_CONFIG_DIR, CONFIG_DIR)
        logger.info("Migrated config from %s to %s", OLD_CONFIG_DIR, CONFIG_DIR)
    except OSError as exc:
        logger.warning("Failed to migrate legacy config: %s", exc)

THEME_PREFERENCES = frozenset({"dark", "light", "system"})
VALID_THEMES = THEME_PREFERENCES


def normalize_theme(value: str) -> str:
    """Return a valid stored theme preference, defaulting to dark."""
    return value if value in THEME_PREFERENCES else "dark"


@dataclass
class Config:
    """Application configuration."""
    api_key: str = ""
    default_folder: str = ""
    cache_enabled: bool = True
    last_cbl_directory: str = ""
    getcomics_download_folder: str = ""
    auto_enrich_after_download: bool = True
    theme: str = "dark"

    def save(self) -> None:
        """Save config to file."""
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(dir=CONFIG_DIR, suffix=".json")
        tmp_path = Path(name)
        os.close(fd)
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(asdict(self), f, indent=2)
            os.replace(tmp_path, CONFIG_FILE)
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise

    @classmethod
    def load(cls) -> "Config":
        """Load config from file."""
        _migrate_legacy_config()
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE) as f:
                    data = json.load(f)
                    if not isinstance(data, dict):
                        raise TypeError("configuration root must be a JSON object")
                    known_fields = {config_field.name for config_field in fields(cls)}
                    kwargs = {
                        key: value
                        for key, value in data.items()
                        if key in known_fields
                    }
                    if "theme" in kwargs:
                        kwargs["theme"] = normalize_theme(kwargs["theme"])
                    return cls(**kwargs)
            except (json.JSONDecodeError, IOError, TypeError) as e:
                logger.warning(f"Failed to load config: {e}")
        return cls()
