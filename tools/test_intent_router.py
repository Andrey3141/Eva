"""
Тесты IntentRouter — каскадной логики.

Проверяют:
  - локально уверенно → LLM не вызывается;
  - локально не уверенно → LLM fallback;
  - LLM даёт intent → source="llm", used_llm=True;
  - LLM не уверен → unknown;
  - Fusion конфликт → LLM fallback.

FakeEmbeddingProvider:
  известные ключевые слова → конкретные оси;
  неизвестный текст         → НУЛЕВОЙ вектор (не привязан к answer!).
"""
import numpy as np
import pytest

from assistant.intent.router.embedding_router import EmbeddingRouter
from assistant.intent.router.fusion import IntentFusion
from assistant.intent.router.llm_router import LLMIntentRouter
from assistant.intent.router.ml_classifier import MLIntentClassifier
from assistant.intent.router.router import IntentRouter
from assistant.intent.router.types import IntentPrediction


class FakeEmbeddingProvider:
    def __init__(self, dim=8):
        self._dim = dim

    def embed(self, texts, role="passage"):
        out = []
        for t in texts:
            low = (t or "").lower()
            vec = np.zeros(self._dim, dtype="float32")

            if "видео" in low or "ролик" in low:
                vec[0] = 1.0
            elif "презентац" in low or "слайд" in low:
                vec[1] = 1.0
            elif "иванов" in low or "сидоров" in low or "петров" in low:
                vec[2] = 1.0
            elif "следующ" in low or "дальше" in low:
                vec[3] = 1.0
            elif "привет" in low or "как дела" in low or "плюс" in low:
                vec[4] = 1.0
            # else: остаётся нулевым

            n = float(np.linalg.norm(vec))
            if n > 0:
                vec = vec / n
            out.append(vec.tolist())
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
    "answer": ["привет", "как дела", "сколько будет два плюс два"],
}


def _make_router(llm_responses=None, threshold=0.75):
    llm = FakeLLM(llm_responses)
    router = IntentRouter(
        embedding_router=EmbeddingRouter(EXAMPLES, FakeEmbeddingProvider(),
                                         min_score=0.3),
        ml_classifier=MLIntentClassifier(EXAMPLES, min_confidence=0.1),
        fusion=IntentFusion(min_individual=0.5, agree_bonus=0.05),
        llm_router=LLMIntentRouter(llm),
        confidence_threshold=threshold,
    )
    return router, llm


# --- 1. Локально уверенно → LLM не вызывается ---

def test_local_confident_does_not_call_llm():
    router, llm = _make_router()
    decision = router.route("включи видео")
    assert decision.intent.name == "open_video"
    assert decision.used_llm is False
    assert llm.calls == 0


# --- 2. Локально не уверенно → LLM fallback ---

def test_local_unconfident_calls_llm():
    router, llm = _make_router([
        '{"intent": "grade_student", "confidence": 0.9, '
        '"params": {"student": "Иванову", "grade": 4}}',
    ])
    decision = router.route("абракадабра зют фыр")
    assert decision.used_llm is True
    assert llm.calls == 1
    assert decision.intent.name == "grade_student"
    assert decision.intent.params.get("student") == "Иванову"


# --- 3. LLM не уверен → UNKNOWN ---

def test_llm_low_confidence_returns_unknown():
    router, llm = _make_router([
        '{"intent": "open_video", "confidence": 0.3, "params": {}}',
    ])
    decision = router.route("абсолютно непонятная фраза")
    assert decision.intent.name == "unknown"
    assert decision.source == "unknown"
    assert decision.used_llm is True
    assert llm.calls == 1


# --- 4. LLM падает → unknown ---

def test_llm_failure_returns_unknown():
    class BrokenLLM:
        def __init__(self):
            self.calls = 0

        def chat(self, *_a, **_kw):
            self.calls += 1
            raise RuntimeError("llm down")

        def name(self):
            return "broken"

    llm = BrokenLLM()
    router = IntentRouter(
        embedding_router=EmbeddingRouter(EXAMPLES, FakeEmbeddingProvider(),
                                         min_score=0.99),
        ml_classifier=MLIntentClassifier(EXAMPLES),
        fusion=IntentFusion(min_individual=0.99),
        llm_router=LLMIntentRouter(llm),
        confidence_threshold=0.75,
    )
    decision = router.route("совсем непонятно")
    assert decision.intent.name in ("answer", "unknown")


# --- 5. parse() возвращает один Intent ---

def test_parse_returns_single_intent():
    router, llm = _make_router()
    intents = router.parse("включи видео")
    assert len(intents) == 1
    assert intents[0].name == "open_video"
    assert llm.calls == 0


# --- 6. Метрика llm_calls ---

def test_llm_calls_counter():
    router, llm = _make_router([
        '{"intent": "answer", "confidence": 0.9, "params": {}}',
        '{"intent": "answer", "confidence": 0.9, "params": {}}',
    ])
    router.route("совсем непонятное 1")
    router.route("совсем непонятное 2")
    router.route("включи видео")   # локально уверенно, LLM не вызывается
    assert router.llm_calls == 2
    assert llm.calls == 2


# --- 7. Fusion конфликт → LLM fallback ---

def test_fusion_disagreement_goes_to_llm():
    """
    embedding = open_video 1.0
    ML        = answer     0.5
    → Fusion.intent = None (конфликт двух конкретных, победитель не выбирается)
    → LLM fallback
    → open_video
    """
    class EmbVideo:
        def embed(self, texts, role="passage"):
            out = []
            for _ in texts:
                v = np.zeros(8, dtype="float32")
                v[0] = 1.0
                out.append(v.tolist())
            return out
        @property
        def dimension(self):
            return 8

    class MlAnswer:
        def __init__(self, examples): pass
        def predict(self, text):
            return IntentPrediction(intent="answer", confidence=0.5, source="ml")

    llm = FakeLLM(['{"intent": "open_video", "confidence": 0.9, "params": {}}'])
    router = IntentRouter(
        embedding_router=EmbeddingRouter(EXAMPLES, EmbVideo(), min_score=0.1),
        ml_classifier=MlAnswer(EXAMPLES),
        fusion=IntentFusion(min_individual=0.5),
        llm_router=LLMIntentRouter(llm),
        confidence_threshold=0.75,
    )
    decision = router.route("какой-то текст")
    assert decision.used_llm is True
    assert llm.calls == 1
    assert decision.intent.name == "open_video"
