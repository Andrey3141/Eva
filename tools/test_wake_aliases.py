"""
Тесты фактического поведения KeywordWakeDetector с разными
ASSISTANT_NAME/ASSISTANT_ALIASES.

Проверяет:
  - имя без алиасов работает;
  - имя + алиасы работают;
  - старое "Алеся"/"Ассистент" не работает после смены имени;
  - очистка алиасов отключает старые алиасы;
  - смена Config после создания уже существующего детектора
    начинает работать без пересоздания (детектор читает Config
    на каждом detect());
  - пунктуация: запятая, пробел, латиница;
  - явные static aliases в конструкторе игнорируют Config.

Запуск:
    pytest -v tools/test_wake_aliases.py
"""
import os
import sys
from types import SimpleNamespace

import pytest

from assistant.wake.keyword_detector import KeywordWakeDetector


def _apply_cfg(monkeypatch, name, aliases):
    """
    Подменяет Config для детектора. Детектор читает
    `config.Config` через `import config`, поэтому подменяем
    именно атрибут Config в модуле config.
    """
    import config as config_module
    fake = SimpleNamespace(
        ASSISTANT_NAME=name,
        ASSISTANT_ALIASES=list(aliases),
    )
    monkeypatch.setattr(config_module, "Config", fake)


# --- Пункт 3: имя без алиасов ---

def test_new_name_only_works(monkeypatch):
    _apply_cfg(monkeypatch, "Луна", [])
    d = KeywordWakeDetector()

    assert d.detect("Луна, привет").is_addressed is True
    assert d.detect("Луна привет").is_addressed is True
    assert d.detect("луна, привет").is_addressed is True


# --- Пункт 3: старое имя не работает ---

def test_old_names_not_matching(monkeypatch):
    _apply_cfg(monkeypatch, "Луна", [])
    d = KeywordWakeDetector()

    assert d.detect("Алеся, привет").is_addressed is False
    assert d.detect("Ассистент, привет").is_addressed is False


# --- Пункт 3: имя + алиасы ---

def test_name_plus_aliases(monkeypatch):
    _apply_cfg(monkeypatch, "Луна", ["луночка", "luna"])
    d = KeywordWakeDetector()

    assert d.detect("Луна, привет").is_addressed is True
    assert d.detect("Луночка, привет").is_addressed is True
    assert d.detect("luna, hello").is_addressed is True
    assert d.detect("Ассистент, привет").is_addressed is False


# --- Пункт 3: пунктуация ---

def test_punctuation_variants(monkeypatch):
    _apply_cfg(monkeypatch, "Луна", ["луночка", "luna"])
    d = KeywordWakeDetector()

    r1 = d.detect("Луна, привет")
    assert r1.is_addressed is True
    assert r1.cleaned_text == "привет"

    r2 = d.detect("Луна привет")
    assert r2.is_addressed is True
    assert r2.cleaned_text == "привет"

    r3 = d.detect("луночка, привет")
    assert r3.is_addressed is True
    assert r3.cleaned_text == "привет"

    r4 = d.detect("luna, hello")
    assert r4.is_addressed is True
    assert r4.cleaned_text == "hello"


# --- Пункт 3: смена имени без пересоздания детектора ---

def test_switch_name_without_recreating_detector(monkeypatch):
    _apply_cfg(monkeypatch, "Луна", [])
    d = KeywordWakeDetector()

    assert d.detect("Луна, привет").is_addressed is True
    assert d.detect("Алеся, привет").is_addressed is False

    # Меняем Config, НЕ пересоздавая детектор.
    _apply_cfg(monkeypatch, "Алеся", [])

    assert d.detect("Алеся, привет").is_addressed is True
    assert d.detect("Луна, привет").is_addressed is False


# --- Пункт 4: явные static aliases ---

def test_static_aliases_ignore_config(monkeypatch):
    _apply_cfg(monkeypatch, "Луна", [])
    d = KeywordWakeDetector(aliases=["специально"])

    assert d.detect("специально, привет").is_addressed is True
    assert d.detect("Луна, привет").is_addressed is False


# --- Пункт 3: реальный путь SettingsStore → Config → детектор ---

def test_settings_roundtrip_new_name(tmp_path):
    from assistant.ui.settings_store import SettingsStore
    from config import Config

    saved_name = Config.ASSISTANT_NAME
    saved_aliases = list(Config.ASSISTANT_ALIASES)
    try:
        store = SettingsStore(path=tmp_path / "settings.json")
        store.save_from({
            "ASSISTANT_NAME": "Луна",
            "ASSISTANT_ALIASES": "луночка, luna",
        })

        assert Config.ASSISTANT_NAME == "Луна"
        assert set(Config.ASSISTANT_ALIASES) == {"луночка", "luna"}

        d = KeywordWakeDetector()
        assert d.detect("Луна, привет").is_addressed is True
        assert d.detect("Луночка, привет").is_addressed is True
        assert d.detect("luna, hello").is_addressed is True
        assert d.detect("Алеся, привет").is_addressed is False
        assert d.detect("Ассистент, привет").is_addressed is False
    finally:
        Config.ASSISTANT_NAME = saved_name
        Config.ASSISTANT_ALIASES = saved_aliases


def test_settings_clear_aliases(tmp_path):
    from assistant.ui.settings_store import SettingsStore
    from config import Config

    saved_name = Config.ASSISTANT_NAME
    saved_aliases = list(Config.ASSISTANT_ALIASES)
    try:
        store = SettingsStore(path=tmp_path / "settings.json")
        store.save_from({
            "ASSISTANT_NAME": "Луна",
            "ASSISTANT_ALIASES": "луночка",
        })
        assert "луночка" in Config.ASSISTANT_ALIASES

        # Очищаем алиасы — должно остаться только имя.
        store.save_from({
            "ASSISTANT_NAME": "Луна",
            "ASSISTANT_ALIASES": "",
        })
        assert Config.ASSISTANT_ALIASES == []

        d = KeywordWakeDetector()
        assert d.detect("Луночка, привет").is_addressed is False
        assert d.detect("Луна, привет").is_addressed is True
    finally:
        Config.ASSISTANT_NAME = saved_name
        Config.ASSISTANT_ALIASES = saved_aliases


def test_settings_old_name_not_matching(tmp_path):
    from assistant.ui.settings_store import SettingsStore
    from config import Config

    saved_name = Config.ASSISTANT_NAME
    saved_aliases = list(Config.ASSISTANT_ALIASES)
    try:
        store = SettingsStore(path=tmp_path / "settings.json")
        store.save_from({
            "ASSISTANT_NAME": "Луна",
            "ASSISTANT_ALIASES": "",
        })
        assert Config.ASSISTANT_NAME == "Луна"
        assert Config.ASSISTANT_ALIASES == []

        d = KeywordWakeDetector()
        assert d.detect("Луна, привет").is_addressed is True
        assert d.detect("Алеся, привет").is_addressed is False
        assert d.detect("Ассистент, привет").is_addressed is False
    finally:
        Config.ASSISTANT_NAME = saved_name
        Config.ASSISTANT_ALIASES = saved_aliases


def run_all():
    print("Запуск через pytest: pytest -v tools/test_wake_aliases.py", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(run_all())
