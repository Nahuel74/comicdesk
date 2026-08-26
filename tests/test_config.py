"""Regression tests for configuration loading."""

import json

import cbl_maker.config as config_module
from cbl_maker.config import Config


def test_load_ignores_unknown_json_keys(tmp_path, monkeypatch):
    """Older/newer config files may contain fields this version does not know."""
    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps({
            "api_key": "configured-key",
            "default_folder": "/comics",
            "cache_enabled": False,
            "future_setting": "ignored",
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(config_module, "CONFIG_FILE", config_file)

    config = Config.load()

    assert config == Config(
        api_key="configured-key",
        default_folder="/comics",
        cache_enabled=False,
    )
