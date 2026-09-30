"""
Интеграция IntentRouter с AssistantCore.

Проверяет, что Core не знает о каскаде — получает обычный IntentParser.

FakeEmbeddingProvider:
  известные ключевые слова → конкретные оси;
  неизвестный текст         → НУЛЕВОЙ вектор (не answer!).
"""
import numpy as np
import pytest

from assistant.core import AssistantCore
from assistant.wake.keyword_detector import KeywordWakeDetector
from assistant.response.echo_response import EchoResponseGenerator
from assistant.actions.base import ActionRegistry, ActionContext
from assistant.confirmation import KeywordConfirmationParser
from assistant.intent.router.embedding_router import EmbeddingRouter
from assistant.intent.router.fusion import IntentFusion
from assistant.intent.router.llm_router import LLMIntentRouter
from assistant.intent.router.ml_classifier import MLIntentClassifier
from assistant.intent.router.router import IntentRouter


class FakeSTT:
    def __init__(self):
        self.text = ""

    def transcribe(self, audio, sample_rate):
        return self.text


class SilentTTS:
    def __init__(self):
        self.spoken = []

    def speak(self, text):
        if text:
            self.spoken.append(text)


class FakeEmbeddingProvider:
    """
    Известные кластеры → конкретные оси.
    Неизвестный текст → нулевой вектор (cosine = 0 → нет привязки).
    """

    def __init__(self, dim=8):
        self._dim = dim

    def embed(self, texts, role="passage"):
        out = []
        for t in texts:
            low = (t or "").lower()
            v = np.zeros(self._dim, dtype="float32")

            if "видео" in low or "ролик" in low:
                v[0] = 1.0
            elif "презентац" in low or "слайд" in low:
                v[1] = 1.0
            elif "иванов" in low or "сидоров" in low:
                v[2] = 1.0
            elif "дальше" in low or "следующ" in low:
                v[3] = 1.0
            elif "привет" in low or "как дела" in low:
                v[4] = 1.0
            # else: остаётся нулевым

            n = float(np.linalg.norm(v))
            if n > 0:
                v = v / n
            out.append(v.tolist())
        return out

    @property
    def dimension(self):
        return self._dim


class FakeLLM:
    def __init__(self, responses=None):
        self._responses = list(responses or [])
        self.calls = 0

    def chat(self, user_message, system_prompt=None):
        self.calls += 1
        if not self._responses:
            return '{"intent": "answer", "confidence": 0.1, "params": {}}'
        return self._responses.pop(0)

    def name(self):
        return "fake"


EXAMPLES = {
    "open_video": ["включи видео", "покажи видео", "запусти ролик"],
    "open_presentation": ["открой презентацию", "покажи слайды"],
    "grade_student": ["поставь Иванову четыре", "Сидоров два"],
    "next_slide": ["следующий слайд", "дальше"],
    "answer": ["привет", "как дела"],
}


@pytest.fixture
def core_with_router():
    stt = FakeSTT()
    tts = SilentTTS()
    llm = FakeLLM()

    router = IntentRouter(
        embedding_router=EmbeddingRouter(EXAMPLES, FakeEmbeddingProvider(),
                                         min_score=0.3),
        ml_classifier=MLIntentClassifier(EXAMPLES, min_confidence=0.1),
        fusion=IntentFusion(min_individual=0.5),
        llm_router=LLMIntentRouter(llm),
        confidence_threshold=0.75,
    )

    core = AssistantCore(
        stt=stt,
        wake=KeywordWakeDetector(aliases=["ассистент"]),
        intent_parser=router,
        response_gen=EchoResponseGenerator(),
        actions=ActionRegistry(),
        tts=tts,
        confirmation_parser=KeywordConfirmationParser(),
        context=ActionContext(addressed_to_assistant=True),
    )
    return core, stt, tts, router, llm


def test_integration_open_video_local(core_with_router):
    core, stt, tts, router, llm = core_with_router
    stt.text = "Ассистент, включи видео"
    r = core.handle_audio(np.zeros(16000, dtype="float32"), 16000)
    assert r.is_addressed is True
    assert r.intent.name == "open_video"
    assert llm.calls == 0


def test_integration_unknown_does_not_call_response(core_with_router):
    core, stt, tts, router, llm = core_with_router
    stt.text = "Ассистент, абракадабра зют фыр"
    r = core.handle_audio(np.zeros(16000, dtype="float32"), 16000)
    assert r.intent.name == "unknown"
    assert "не поняла" in r.final_speech.lower() or "уточните" in r.final_speech.lower()
