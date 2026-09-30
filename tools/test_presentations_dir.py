"""
Тесты настройки папки презентаций (paths.presentations_dir)
и связанных параметров threshold/margin.
"""
import os
import sys
from pathlib import Path

import pytest

from assistant import paths


def test_desktop_dir_is_absolute():
    d = paths._desktop_dir()
    assert isinstance(d, Path)
    assert d.is_absolute()


def test_default_presentations_dir_under_desktop():
    d = paths.default_presentations_dir()
    assert d.name == "Презентации EVA"
    assert d.parent == paths._desktop_dir()


def test_presentations_dir_creates_directory(monkeypatch, tmp_path):
    custom = tmp_path / "pres"
    monkeypatch.setenv("PRESENTATIONS_DIR", str(custom))
    d = paths.presentations_dir()
    assert d == custom
    assert d.exists()
    assert d.is_dir()


def test_presentations_dir_env_override(monkeypatch, tmp_path):
    custom = tmp_path / "custom_pres"
    monkeypatch.setenv("PRESENTATIONS_DIR", str(custom))
    assert paths.presentations_dir() == custom


def test_describe_contains_presentations():
    text = paths.describe()
    assert "Presentations" in text


def test_config_presentations_dir_is_string():
    from config import Config
    assert isinstance(Config.PRESENTATIONS_DIR, str)
    assert Config.PRESENTATIONS_DIR


# ---------------------------------------------------------------------------
# Настройки threshold и margin
# ---------------------------------------------------------------------------

def test_config_presentation_threshold_default():
    from config import Config
    assert Config.PRESENTATION_MATCH_THRESHOLD == pytest.approx(0.70)


def test_config_presentation_margin_default():
    from config import Config
    assert Config.PRESENTATION_AMBIGUITY_MARGIN == pytest.approx(0.05)


def test_settings_store_saves_threshold(tmp_path):
    from assistant.ui.settings_store import SettingsStore
    from config import Config

    saved = Config.PRESENTATION_MATCH_THRESHOLD
    try:
        store = SettingsStore(path=tmp_path / "settings.json")
        store.save_from({"PRESENTATION_MATCH_THRESHOLD": 0.85})
        assert Config.PRESENTATION_MATCH_THRESHOLD == pytest.approx(0.85)
    finally:
        Config.PRESENTATION_MATCH_THRESHOLD = saved


def test_settings_store_saves_margin(tmp_path):
    from assistant.ui.settings_store import SettingsStore
    from config import Config

    saved = Config.PRESENTATION_AMBIGUITY_MARGIN
    try:
        store = SettingsStore(path=tmp_path / "settings.json")
        store.save_from({"PRESENTATION_AMBIGUITY_MARGIN": 0.10})
        assert Config.PRESENTATION_AMBIGUITY_MARGIN == pytest.approx(0.10)
    finally:
        Config.PRESENTATION_AMBIGUITY_MARGIN = saved


def test_settings_store_reloads_threshold(tmp_path):
    from assistant.ui.settings_store import SettingsStore

    p = tmp_path / "settings.json"
    s1 = SettingsStore(path=p)
    s1.save_from({"PRESENTATION_MATCH_THRESHOLD": 0.55})

    s2 = SettingsStore(path=p)
    assert s2.get("PRESENTATION_MATCH_THRESHOLD") == pytest.approx(0.55)


def run_all():
    print("Запуск через pytest: pytest -v tools/test_presentations_dir.py",
          flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(run_all())
