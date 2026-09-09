"""Regression tests for configuration loading."""

import json

import comicdesk.config as config_module
from comicdesk.config import Config, normalize_theme


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


def test_load_persists_theme_setting(tmp_path, monkeypatch):
    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps({"theme": "light"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(config_module, "CONFIG_FILE", config_file)

    config = Config.load()

    assert config.theme == "light"


def test_load_normalizes_invalid_theme(tmp_path, monkeypatch):
    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps({"theme": "sepia"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(config_module, "CONFIG_FILE", config_file)

    config = Config.load()

    assert config.theme == "dark"


def test_save_includes_theme(tmp_path, monkeypatch):
    config_file = tmp_path / "config.json"
    monkeypatch.setattr(config_module, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config_module, "CONFIG_FILE", config_file)

    Config(theme="light").save()

    data = json.loads(config_file.read_text(encoding="utf-8"))
    assert data["theme"] == "light"


def test_normalize_theme_helper():
    assert normalize_theme("light") == "light"
    assert normalize_theme("unknown") == "dark"


def test_migrates_legacy_config_dir(tmp_path, monkeypatch):
    legacy_dir = tmp_path / "legacy"
    legacy_dir.mkdir()
    (legacy_dir / "config.json").write_text(
        json.dumps({"api_key": "legacy-key"}),
        encoding="utf-8",
    )
    new_dir = tmp_path / "comicdesk"

    monkeypatch.setattr(config_module, "OLD_CONFIG_DIR", legacy_dir)
    monkeypatch.setattr(config_module, "CONFIG_DIR", new_dir)
    monkeypatch.setattr(config_module, "CONFIG_FILE", new_dir / "config.json")

    config = Config.load()

    assert new_dir.exists()
    assert config.api_key == "legacy-key"
