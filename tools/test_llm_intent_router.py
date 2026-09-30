"""
Тесты LLMIntentRouter — обёртки над LLMIntentParser.
LLM — FakeLLM, без сети.
"""
import pytest

from assistant.intent.router.llm_router import LLMIntentRouter


class FakeLLM:
    def __init__(self, responses=None):
        self._responses = list(responses or [])
        self.calls = 0
        self.last_user = None
        self.last_system = None

    def chat(self, user_message, system_prompt=None):
        self.calls += 1
        self.last_user = user_message
        self.last_system = system_prompt
        if not self._responses:
            return ""
        return self._responses.pop(0)

    def name(self):
        return "fake"


def test_llm_router_returns_prediction_from_valid_json():
    llm = FakeLLM(['{"intent": "open_video", "confidence": 0.92, '
                   '"params": {"query": "трансформаторы"}}'])
    router = LLMIntentRouter(llm)
    pred = router.route("включи видео про трансформаторы")
    assert pred.intent == "open_video"
    assert pred.confidence == pytest.approx(0.92)
    assert pred.params.get("query") == "трансформаторы"
    assert pred.source == "llm"


def test_llm_router_answer():
    llm = FakeLLM(['{"intent": "answer", "confidence": 0.94, "params": {}}'])
    router = LLMIntentRouter(llm)
    pred = router.route("сколько будет 2+2")
    assert pred.intent == "answer"
    assert pred.confidence == pytest.approx(0.94)


def test_llm_router_invalid_json_returns_low_confidence():
    llm = FakeLLM(["не JSON"])
    router = LLMIntentRouter(llm)
    pred = router.route("...")
    # LLMIntentParser при невалидном JSON отдаёт answer с confidence 0.5.
    assert pred.intent == "answer"
    assert pred.confidence <= 0.5


def test_llm_router_empty_text_no_call():
    llm = FakeLLM(["ignored"])
    router = LLMIntentRouter(llm)
    pred = router.route("")
    assert pred.intent == ""
    assert llm.calls == 0


def test_llm_router_system_prompt_is_intent_only():
    """
    Компактный системный промпт для классификации, а не для ответа.
    """
    llm = FakeLLM(['{"intent": "answer", "confidence": 0.9}'])
    router = LLMIntentRouter(llm)
    router.route("привет")
    assert llm.last_system is not None
    assert "intent" in llm.last_system.lower() or "JSON" in llm.last_system
