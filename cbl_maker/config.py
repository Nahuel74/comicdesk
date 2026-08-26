"""Configuration management for CBL Maker."""

import json
from pathlib import Path
from dataclasses import dataclass, asdict


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
            with open(CONFIG_FILE) as f:
                data = json.load(f)
                return cls(**data)
        return cls()
