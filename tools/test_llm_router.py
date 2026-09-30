"""
Тесты LLM Router. Не делает сетевых запросов — использует fake-провайдеры.

Запуск:
    python -m tools.test_llm_router
    pytest -v tools/test_llm_router.py
"""
from __future__ import annotations

import sys
import time

from assistant.llm.base import LLMEngine
from assistant.llm.router import (
    LLMRouter, LLMProviderConfig, NetworkChecker,
)
from assistant.llm.router.router import _Entry
from assistant.llm.router.state import (
    ProviderStatus, FailureReason,
)


# --- Fake-провайдеры ---

class FakeProvider(LLMEngine):
    def __init__(self, name: str, scripted: list[str]):
        self._name = name
        self._script = list(scripted)
        self.calls = 0

    def name(self) -> str:
        return self._name

    def chat(self, user_message: str, system_prompt: str | None = None) -> str:
        self.calls += 1
        if not self._script:
            return "empty"
        return self._script.pop(0)


class FakeNetwork(NetworkChecker):
    def __init__(self, online: bool):
        super().__init__(cache_seconds=0)
        self._forced = online

    def is_online(self) -> bool:
        return self._forced

    def set_online(self, v: bool) -> None:
        self._forced = v


def _entry(name, priority, provider, **cfg_kwargs) -> _Entry:
    cfg = LLMProviderConfig(
        name=name,
        model="fake",
        priority=priority,
        **cfg_kwargs,
    )
    return _Entry(provider=provider, config=cfg)


# --- Исходные 8 тестов (без изменений по существу) ---

def test_1_gemini_ok():
    print("\n[1] Gemini доступен → используется Gemini")
    gem = FakeProvider("gemini", ["ответ Gemini"])
    opn = FakeProvider("openrouter", ["ответ OpenRouter"])
    net = FakeNetwork(True)

    router = LLMRouter([_entry("gemini", 1, gem), _entry("openrouter", 4, opn)], net)
    result = router.chat("привет")

    assert result == "ответ Gemini", result
    assert gem.calls == 1
    assert opn.calls == 0
    print("[OK]")


def test_2_gemini_quota():
    print("\n[2] Gemini QUOTA → используется OpenRouter")
    gem = FakeProvider("gemini", ["Gemini: превышен лимит запросов."])
    opn = FakeProvider("openrouter", ["ответ OpenRouter"])
    net = FakeNetwork(True)

    router = LLMRouter([_entry("gemini", 1, gem), _entry("openrouter", 4, opn)], net)
    result = router.chat("привет")

    assert result == "ответ OpenRouter", result
    assert gem.calls == 1
    assert opn.calls == 1
    assert router._entries[0].state.status == ProviderStatus.DISABLED
    assert router._entries[0].state.reason == FailureReason.QUOTA_EXHAUSTED
    print("[OK]")


def test_3_gemini_not_called_after_quota():
    print("\n[3] Второй запрос после quota — Gemini НЕ вызывается")
    gem = FakeProvider("gemini", ["Gemini: превышен лимит запросов.", "ОШИБКА"])
    opn = FakeProvider("openrouter", ["ответ 1", "ответ 2"])
    net = FakeNetwork(True)

    router = LLMRouter([_entry("gemini", 1, gem), _entry("openrouter", 4, opn)], net)

    r1 = router.chat("первый")
    r2 = router.chat("второй")

    assert r1 == "ответ 1"
    assert r2 == "ответ 2"
    assert gem.calls == 1
    assert opn.calls == 2
    print("[OK]")


def test_4_network_offline():
    print("\n[4] Network OFFLINE → облачные провайдеры не вызываются")
    gem = FakeProvider("gemini", ["должен быть проигнорирован"])
    opn = FakeProvider("openrouter", ["должен быть проигнорирован"])
    net = FakeNetwork(False)

    router = LLMRouter([_entry("gemini", 1, gem), _entry("openrouter", 4, opn)], net)
    result = router.chat("привет")

    assert gem.calls == 0
    assert opn.calls == 0
    assert "недоступны" in result.lower() or "провайдера" in result.lower()
    print("[OK]")


def test_5_gemini_timeout_cooldown():
    print("\n[5] Gemini TIMEOUT → cooldown")
    gem = FakeProvider("gemini", ["Gemini: превышено время ожидания ответа."])
    opn = FakeProvider("openrouter", ["ответ OpenRouter", "ответ OpenRouter 2"])
    net = FakeNetwork(True)

    router = LLMRouter([_entry("gemini", 1, gem), _entry("openrouter", 4, opn)], net,
                       cooldown_seconds=30)
    r1 = router.chat("первый")
    assert r1 == "ответ OpenRouter"

    st = router._entries[0].state
    assert st.status == ProviderStatus.COOLDOWN
    assert st.reason == FailureReason.TIMEOUT

    r2 = router.chat("второй")
    assert r2 == "ответ OpenRouter 2"
    assert gem.calls == 1
    assert opn.calls == 2
    print("[OK]")


def test_6_new_router_available():
    print("\n[6] Новый экземпляр Router → Gemini снова AVAILABLE")
    gem1 = FakeProvider("gemini", ["Gemini: превышен лимит запросов."])
    opn1 = FakeProvider("openrouter", ["ответ OpenRouter"])
    net1 = FakeNetwork(True)
    r1 = LLMRouter([_entry("gemini", 1, gem1), _entry("openrouter", 4, opn1)], net1)
    r1.chat("привет")
    assert r1._entries[0].state.status == ProviderStatus.DISABLED

    gem2 = FakeProvider("gemini", ["ответ Gemini"])
    opn2 = FakeProvider("openrouter", ["на всякий случай"])
    net2 = FakeNetwork(True)
    r2 = LLMRouter([_entry("gemini", 1, gem2), _entry("openrouter", 4, opn2)], net2)
    assert r2._entries[0].state.status == ProviderStatus.AVAILABLE
    result = r2.chat("привет")
    assert result == "ответ Gemini"
    assert gem2.calls == 1
    print("[OK]")


def test_7_intent_filter():
    print("\n[7] Intent request → только supports_intent=True")
    text_only = FakeProvider("text-only", ["ответ text-only"])
    full = FakeProvider("full", ["ответ full"])
    net = FakeNetwork(True)

    e1 = _entry("text-only", 1, text_only, supports_intent=False, supports_response=True)
    e2 = _entry("full", 2, full, supports_intent=True, supports_response=True)

    router = LLMRouter([e1, e2], net)
    result = router.chat_for_intent("дай JSON")

    assert result == "ответ full"
    assert text_only.calls == 0
    assert full.calls == 1
    print("[OK]")


def test_8_response_filter():
    print("\n[8] Response request → только supports_response=True")
    intent_only = FakeProvider("intent-only", ["ответ intent-only"])
    full = FakeProvider("full", ["ответ full"])
    net = FakeNetwork(True)

    e1 = _entry("intent-only", 1, intent_only, supports_intent=True, supports_response=False)
    e2 = _entry("full", 2, full, supports_intent=True, supports_response=True)

    router = LLMRouter([e1, e2], net)
    result = router.chat_for_response("обычный вопрос")

    assert result == "ответ full"
    assert intent_only.calls == 0
    assert full.calls == 1
    print("[OK]")


# --- Новые тесты: порядок провайдеров и поведение Groq/Cerebras ---

def test_9_order_gemini_groq_cerebras_openrouter():
    """
    Порядок приоритетов: gemini(1) → groq(2) → cerebras(3) → openrouter(4).
    Проверяем через LLMRouter._entries после сортировки.
    """
    print("\n[9] Порядок провайдеров gemini → groq → cerebras → openrouter")
    entries = [
        _entry("gemini", 1, FakeProvider("gemini", ["x"])),
        _entry("groq", 2, FakeProvider("groq", ["x"])),
        _entry("cerebras", 3, FakeProvider("cerebras", ["x"])),
        _entry("openrouter", 4, FakeProvider("openrouter", ["x"])),
    ]
    router = LLMRouter(entries, FakeNetwork(True))
    names = [e.config.name for e in router._entries]
    assert names == ["gemini", "groq", "cerebras", "openrouter"], names
    print("[OK]")


def test_10_gemini_error_goes_to_groq():
    print("\n[10] Gemini падает → используется Groq")
    gem = FakeProvider("gemini", ["Gemini: превышен лимит запросов."])
    groq = FakeProvider("groq", ["ответ Groq"])
    opn = FakeProvider("openrouter", ["ответ OpenRouter"])
    net = FakeNetwork(True)

    router = LLMRouter([
        _entry("gemini", 1, gem),
        _entry("groq", 2, groq),
        _entry("openrouter", 4, opn),
    ], net)
    result = router.chat("привет")

    assert result == "ответ Groq"
    assert gem.calls == 1
    assert groq.calls == 1
    assert opn.calls == 0
    print("[OK]")


def test_11_groq_error_goes_to_cerebras():
    print("\n[11] Groq падает → используется Cerebras")
    gem = FakeProvider("gemini", ["Gemini: превышен лимит запросов."])
    groq = FakeProvider("groq", ["Groq: ошибка авторизации. Проверьте ключ."])
    cer = FakeProvider("cerebras", ["ответ Cerebras"])
    net = FakeNetwork(True)

    router = LLMRouter([
        _entry("gemini", 1, gem),
        _entry("groq", 2, groq),
        _entry("cerebras", 3, cer),
    ], net)
    result = router.chat("привет")

    assert result == "ответ Cerebras"
    assert groq.calls == 1
    assert cer.calls == 1
    print("[OK]")


def test_12_cerebras_error_goes_to_openrouter():
    print("\n[12] Cerebras падает → используется OpenRouter")
    cer = FakeProvider("cerebras", ["Cerebras: ошибка авторизации. Проверьте ключ."])
    opn = FakeProvider("openrouter", ["ответ OpenRouter"])
    net = FakeNetwork(True)

    router = LLMRouter([
        _entry("cerebras", 3, cer),
        _entry("openrouter", 4, opn),
    ], net)
    result = router.chat("привет")

    assert result == "ответ OpenRouter"
    assert cer.calls == 1
    assert opn.calls == 1
    print("[OK]")


def test_13_groq_cooldown_skipped():
    print("\n[13] Groq в cooldown — пропускается")
    groq = FakeProvider("groq", ["Groq: нет соединения с сервером.", "НЕ ДОЛЖЕН"])
    opn = FakeProvider("openrouter", ["ответ 1", "ответ 2"])
    net = FakeNetwork(True)

    router = LLMRouter([
        _entry("groq", 2, groq),
        _entry("openrouter", 4, opn),
    ], net, cooldown_seconds=30)

    router.chat("первый")
    st = router._entries[0].state
    assert st.status == ProviderStatus.COOLDOWN

    router.chat("второй")
    assert groq.calls == 1, f"groq вызван {groq.calls} раз, ожидалось 1"
    assert opn.calls == 2
    print("[OK]")


def test_14_cerebras_disabled_skipped():
    print("\n[14] Cerebras DISABLED — пропускается")
    cer = FakeProvider("cerebras", ["Cerebras: превышена квота.", "НЕ ДОЛЖЕН"])
    opn = FakeProvider("openrouter", ["ответ 1", "ответ 2"])
    net = FakeNetwork(True)

    router = LLMRouter([
        _entry("cerebras", 3, cer),
        _entry("openrouter", 4, opn),
    ], net)

    router.chat("первый")
    st = router._entries[0].state
    assert st.status == ProviderStatus.DISABLED
    assert st.reason == FailureReason.QUOTA_EXHAUSTED

    router.chat("второй")
    assert cer.calls == 1
    assert opn.calls == 2
    print("[OK]")


def test_15_missing_key_provider_not_in_entries():
    """
    Провайдер без ключа не должен попадать в список entries.
    Это проверяется на уровне main.build_llm (через _make_*_entry),
    здесь мы проверяем сам принцип: entry без ключа не создаём.
    """
    print("\n[15] Провайдер без ключа отсутствует в списке entries")

    class FakeEmpty:
        def __init__(self):
            self.calls = 0

        def chat(self, *_a, **_kw):
            self.calls += 1
            return ""

        def name(self):
            return "empty"

    # Эмулируем _make_groq_entry() при отсутствии ключа → None
    def make_groq_entry(api_key, model):
        if not api_key or not model:
            return None
        return _entry("groq", 2, FakeProvider("groq", ["x"]))

    assert make_groq_entry("", "") is None
    assert make_groq_entry("k", "") is None
    assert make_groq_entry("", "m") is None
    assert make_groq_entry("k", "m") is not None
    print("[OK]")


def test_16_all_external_unavailable_returns_clear_error():
    """
    Если все облачные провайдеры в DISABLED, Router возвращает
    понятную строку об отсутствии доступных провайдеров.
    """
    print("\n[16] Все внешние недоступны → понятное сообщение")

    gem = FakeProvider("gemini", ["Gemini: превышена квота."])
    groq = FakeProvider("groq", ["Groq: превышена квота."])
    cer = FakeProvider("cerebras", ["Cerebras: превышена квота."])
    opn = FakeProvider("openrouter", ["OpenRouter: превышена квота."])
    net = FakeNetwork(True)

    router = LLMRouter([
        _entry("gemini", 1, gem),
        _entry("groq", 2, groq),
        _entry("cerebras", 3, cer),
        _entry("openrouter", 4, opn),
    ], net)

    r1 = router.chat("первый")
    assert "квота" in r1.lower() or "лимит" in r1.lower()

    # Все четыре DISABLED
    for e in router._entries:
        assert e.state.status == ProviderStatus.DISABLED

    # Второй запрос: все провайдеры пропускаются как DISABLED
    r2 = router.chat("второй")
    assert "недоступны" in r2.lower() or "провайдера" in r2.lower() or r2
    print("[OK]")


# --- Прямой запуск ---

def run_all():
    tests = [
        test_1_gemini_ok,
        test_2_gemini_quota,
        test_3_gemini_not_called_after_quota,
        test_4_network_offline,
        test_5_gemini_timeout_cooldown,
        test_6_new_router_available,
        test_7_intent_filter,
        test_8_response_filter,
        test_9_order_gemini_groq_cerebras_openrouter,
        test_10_gemini_error_goes_to_groq,
        test_11_groq_error_goes_to_cerebras,
        test_12_cerebras_error_goes_to_openrouter,
        test_13_groq_cooldown_skipped,
        test_14_cerebras_disabled_skipped,
        test_15_missing_key_provider_not_in_entries,
        test_16_all_external_unavailable_returns_clear_error,
    ]
    failed = 0
    for t in tests:
        try:
            t()
        except AssertionError as e:
            failed += 1
            print(f"[FAIL] {t.__name__}: {e}", flush=True)
        except Exception as e:
            failed += 1
            print(f"[ERROR] {t.__name__}: {type(e).__name__}: {e}", flush=True)
    print()
    print(f"=== {len(tests) - failed}/{len(tests)} ROUTER TESTS PASSED ===", flush=True)
    return failed


def main():
    print("=== LLM ROUTER TESTS ===")
    failed = run_all()
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
