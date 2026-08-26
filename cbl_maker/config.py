"""Configuration management for CBL Maker."""

import json
import logging
from pathlib import Path
from dataclasses import asdict, dataclass, fields

logger = logging.getLogger(__name__)

CONFIG_DIR = Path.home() / ".config" / "cbl-maker"
CONFIG_FILE = CONFIG_DIR / "config.json"


@dataclass
class Config:
    """Application configuration."""
    api_key: str = ""
    default_folder: str = ""
    cache_enabled: bool = True

    def save(self) -> None:
        """Save config to file."""
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w") as f:
            json.dump(asdict(self), f, indent=2)

    @classmethod
    def load(cls) -> "Config":
        """Load config from file."""
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE) as f:
                    data = json.load(f)
                    if not isinstance(data, dict):
                        raise TypeError("configuration root must be a JSON object")
                    known_fields = {config_field.name for config_field in fields(cls)}
                    return cls(**{
                        key: value
                        for key, value in data.items()
                        if key in known_fields
                    })
            except (json.JSONDecodeError, IOError, TypeError) as e:
                logger.warning(f"Failed to load config: {e}")
        return cls()
