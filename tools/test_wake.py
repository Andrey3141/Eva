"""
Тесты KeywordWakeDetector — обнаружение обращения к EVA.

ВАЖНО: начиная с новой спецификации Config.ASSISTANT_ALIASES по умолчанию
пуст, а ASSISTANT_NAME = "Алеся" (env). Тесты, которые хотят
обращаться по слову "Ассистент" или "Алеся", должны явно задавать
ASSISTANT_NAME/ASSISTANT_ALIASES через фикстуру. Production-код при
этом не меняется.

Запуск через pytest:
    pytest -v tools/test_wake.py
Прямой запуск:
    python -m tools.test_wake
"""
import sys
from types import SimpleNamespace

import pytest

from assistant.wake.keyword_detector import KeywordWakeDetector


def _apply_cfg(monkeypatch, name, aliases):
    """
    Подменяет config.Config для детектора.
    Детектор читает `config.Config` через `import config`,
    поэтому подменяем атрибут Config в модуле config.
    """
    import config as config_module
    fake = SimpleNamespace(
        ASSISTANT_NAME=name,
        ASSISTANT_ALIASES=list(aliases),
    )
    monkeypatch.setattr(config_module, "Config", fake)


@pytest.fixture
def cfg_assistant(monkeypatch):
    """
    Явно выставляет ASSISTANT_NAME = "Ассистент" и пустые алиасы.
    Это то, что предполагали старые тесты, но теперь задаётся явно.
    """
    _apply_cfg(monkeypatch, "Ассистент", [])
    yield


@pytest.fixture
def cfg_assistant_with_alias(monkeypatch):
    """
    ASSISTANT_NAME = "Ассистент", алиас "алеся" — для теста альтернативного алиаса.
    """
    _apply_cfg(monkeypatch, "Ассистент", ["алеся"])
    yield


def _detect(text: str):
    return KeywordWakeDetector().detect(text)


def test_addressed_with_comma(cfg_assistant):
    r = _detect("Ассистент, привет")
    assert r.is_addressed is True
    assert r.cleaned_text == "привет", r.cleaned_text


def test_addressed_without_comma(cfg_assistant):
    r = _detect("Ассистент привет")
    assert r.is_addressed is True
    assert r.cleaned_text == "привет", r.cleaned_text


def test_addressed_in_middle_of_sentence(cfg_assistant):
    r = _detect("Ассистент, поставь Иванову четыре")
    assert r.is_addressed is True
    assert "поставь" in r.cleaned_text.lower()


def test_not_addressed(cfg_assistant):
    r = _detect("Сидоров завтра будет")
    assert r.is_addressed is False
    assert r.cleaned_text == "Сидоров завтра будет"


def test_not_addressed_empty(cfg_assistant):
    r = _detect("")
    assert r.is_addressed is False


def test_case_insensitive(cfg_assistant):
    r = _detect("ассистент, привет")
    assert r.is_addressed is True
    assert r.cleaned_text == "привет"


def test_alternate_alias(cfg_assistant_with_alias):
    # ASSISTANT_NAME = "Ассистент", алиас "алеся" задан явно.
    r = _detect("Алеся, включи видео")
    assert r.is_addressed is True


def test_cleaned_text_does_not_start_with_separator(cfg_assistant):
    r = _detect("Ассистент, поставь Иванову четыре")
    assert r.cleaned_text and not r.cleaned_text.startswith(",")
    assert not r.cleaned_text.startswith(".")


def test_alias_only_is_addressed(cfg_assistant):
    r = _detect("Ассистент")
    assert r.is_addressed is True
    assert r.cleaned_text


def run_all():
    print("Запуск через pytest: pytest -v tools/test_wake.py", flush=True)
    print("Прямой запуск не поддерживается из-за monkeypatch.", flush=True)
    return 0


def main():
    if not __import__("os").path.exists("assistant"):
        print("Запускать из корня проекта.", flush=True)
        sys.exit(2)
    sys.exit(run_all())


if __name__ == "__main__":
    main()
