"""Shared pytest fixtures."""

import json
from pathlib import Path

import pytest

import comicdesk.config as config_module


@pytest.fixture(autouse=True)
def isolated_comicdesk_config(tmp_path, monkeypatch, request):
    """Keep tests from reading or writing the user's live config directory."""
    if request.node.fspath.basename == "test_config.py":
        return
    config_dir = tmp_path / "comicdesk"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_file = config_dir / "config.json"
    config_file.write_text(json.dumps({"theme": "dark"}), encoding="utf-8")
    monkeypatch.setattr(config_module, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(config_module, "CONFIG_FILE", config_file)
    monkeypatch.setattr(
        config_module,
        "OLD_CONFIG_DIR",
        tmp_path / "legacy-cbl-maker",
    )


@pytest.fixture(autouse=True)
def _non_blocking_api_key_alerts(monkeypatch, request):
    """API key prompts use modal QMessageBox; skip blocking dialogs in automated tests."""
    if request.node.fspath.basename == "test_config.py":
        return

    def _noop_warn_missing_api_key(*_args, **_kwargs):
        return None

    monkeypatch.setattr(
        "comicdesk.ui.api_key_prompt.warn_missing_api_key",
        _noop_warn_missing_api_key,
    )
