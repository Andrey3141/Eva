"""
Интеграционные тесты IntentRouter + ParameterRouter.

Проверяют, что IntentRouter корректно распаковывает результат
ParameterRouter.extract_params() (4 значения) и передаёт params
в финальный Intent.

Fake-провайдеры разделены на две независимые роли:

  - IntentFakeEmbeddingProvider — используется EmbeddingRouter'ом
    для классификации intent. Семантические оси совпадают
    с data/intent_examples.json (open_video / open_presentation /
    grade_student / next_slide / answer).

  - ParameterFakeEmbeddingProvider — используется
    EmbeddingCandidateScorer'ом в ParameterRouter. Семантические оси
    для ролей параметров (topic / student / grade / command / object).

Разные задачи — разные fake-провайдеры. Это исключает ситуацию,
когда fake, настроенный под роли параметров, случайно ломает
классификацию intent'а, и наоборот.
"""
import sys

import numpy as np
import pytest

from assistant.intent.parameter import (
    MLSlotTagger, EmbeddingCandidateScorer, ParameterFusion, ParameterRouter,
    load_parameter_examples,
)
from assistant.intent.router.embedding_router import EmbeddingRouter
from assistant.intent.router.fusion import IntentFusion
from assistant.intent.router.llm_router import LLMIntentRouter
from assistant.intent.router.ml_classifier import MLIntentClassifier
from assistant.intent.router.router import IntentRouter


# ===========================================================================
# Fake для EmbeddingRouter (классификация intent)
# ===========================================================================

class IntentFakeEmbeddingProvider:
    """
    Детерминированный fake для IntentRouter.

    Отдельные оси под каждый intent, чтобы embedding-классификация
    была точной и согласованной с data/intent_examples.json.

    Оси:
      0: open_video
      1: open_presentation
      2: grade_student
      3: next_slide
      4: answer
    """

    def __init__(self, dim: int = 8):
        self._dim = dim

    def embed(self, texts, role="passage"):
        out = []
        for t in texts:
            low = (t or "").lower()
            v = np.zeros(self._dim, dtype="float32")

            # --- open_video ---
            if any(w in low for w in
                   ("видео", "ролик", "видеозапис", "видеофильм")):
                v[0] = 1.0

            # --- open_presentation ---
            elif any(w in low for w in
                     ("презентац", "слайд", "слайдов")):
                v[1] = 1.0

            # --- grade_student ---
            elif any(w in low for w in
                     ("иванов", "сидоров", "петров", "смирнов",
                      "поставь", "выставь")):
                v[2] = 1.0

            # --- next_slide ---
            elif any(w in low for w in
                     ("следующ", "дальше", "переключи", "вперёд", "вперед")):
                v[3] = 1.0

            # --- answer (fallback, но не пустой) ---
            else:
                v[4] = 1.0

            n = float(np.linalg.norm(v))
            if n > 0:
                v = v / n
            out.append(v.tolist())
        return out

    @property
    def dimension(self):
        return self._dim


# ===========================================================================
# Fake для EmbeddingCandidateScorer (роли параметров)
# ===========================================================================

class ParameterFakeEmbeddingProvider:
    """
    Детерминированный fake для ParameterRouter / EmbeddingCandidateScorer.

    Оси:
      0: topic
      1: student
      2: grade-words (оценка, балл, отметка)
      3: command
      4: object
      5: fallback (числа, неизвестное)
    """

    def __init__(self, dim: int = 16):
        self._dim = dim

    def embed(self, texts, role="passage"):
        out = []
        for t in texts:
            low = (t or "").lower()
            v = np.zeros(self._dim, dtype="float32")
            matched = False

            if any(w in low for w in
                   ("тем", "занят", "трансформатор", "электр", "физик",
                    "охране", "труда", "монтаж", "защит", "безопас",
                    "материал", "правил", "руководств", "эксплуатац")):
                v[0] = 1.0
                matched = True
            if any(w in low for w in
                   ("фамил", "ученик", "студент", "фио",
                    "иванов", "сидоров", "петров", "смирнов")):
                v[1] = 1.0
                matched = True
            if any(w in low for w in ("оценк", "балл", "отметк")):
                v[2] = 1.0
                matched = True
            if any(w in low for w in
                   ("команд", "приказ", "действ",
                    "открой", "покажи", "запусти", "включи",
                    "поставь", "выставь", "воспроизведи")):
                v[3] = 1.0
                matched = True
            if any(w in low for w in
                   ("объект", "цель", "презентац", "видео", "ролик",
                    "слайд", "материал", "документ")):
                v[4] = 1.0
                matched = True

            if not matched:
                v[5] = 1.0

            n = float(np.linalg.norm(v))
            if n > 0:
                v = v / n
            out.append(v.tolist())
        return out

    @property
    def dimension(self):
        return self._dim


# ===========================================================================
# Fake LLM: не должен вызываться
# ===========================================================================

class FakeLLM:
    def __init__(self):
        self.calls = 0

    def chat(self, user_message, system_prompt=None):
        self.calls += 1
        return '{"intent": "answer", "confidence": 0.1, "params": {}}'

    def name(self):
        return "fake"


# ===========================================================================
# Примеры для IntentRouter (совпадают с data/intent_examples.json)
# ===========================================================================

INTENT_EXAMPLES = {
    "open_video": [
        "включи видео", "покажи видео", "запусти ролик",
        "включи видеозапись", "открой видео",
    ],
    "open_presentation": [
        "открой презентацию", "покажи презентацию",
        "открой слайды", "покажи слайды",
    ],
    "grade_student": [
        "поставь Иванову четыре", "поставь Сидорову три",
        "Иванов пять", "Сидоров два",
    ],
    "next_slide": ["следующий слайд", "дальше"],
    "answer": [
        "привет", "как дела",
        "сколько будет два плюс два", "сколько будет 25 умножить на 4",
    ],
}


@pytest.fixture(scope="module")
def param_examples():
    return load_parameter_examples()


@pytest.fixture
def intent_router(param_examples):
    intent_provider = IntentFakeEmbeddingProvider()
    param_provider = ParameterFakeEmbeddingProvider()

    ml = MLSlotTagger(param_examples, min_confidence=0.10)
    emb = EmbeddingCandidateScorer(
        provider=param_provider,
        max_span_tokens=5,
        top_k=5,
        extra_candidates=3,
    )
    fusion = ParameterFusion(min_ml=0.30, min_emb=0.30, agree_bonus=0.10)
    param_router = ParameterRouter(ml, emb, fusion)

    llm = FakeLLM()
    router = IntentRouter(
        embedding_router=EmbeddingRouter(
            INTENT_EXAMPLES, intent_provider, min_score=0.3,
        ),
        ml_classifier=MLIntentClassifier(INTENT_EXAMPLES, min_confidence=0.1),
        fusion=IntentFusion(min_individual=0.5, agree_bonus=0.05),
        llm_router=LLMIntentRouter(llm),
        confidence_threshold=0.5,
        parameter_router=param_router,
    )
    return router, llm


# ---------------------------------------------------------------------------
# 1. Регрессия: интеграция IntentRouter + ParameterRouter
# ---------------------------------------------------------------------------

def test_presentation_with_topic(intent_router):
    router, _ = intent_router
    decision = router.route("открой презентации итоговые занятия")
    assert decision.intent.name == "open_presentation", (
        f"intent={decision.intent.name}, "
        f"params={decision.intent.params}"
    )
    assert decision.intent.params.get("topic") == "итоговые занятия", (
        f"params={decision.intent.params}"
    )


def test_video_with_topic(intent_router):
    router, _ = intent_router
    decision = router.route(
        "открой видео руководство по эксплуатации кассового аппарата"
    )
    assert decision.intent.name == "open_video", (
        f"intent={decision.intent.name}"
    )
    topic = decision.intent.params.get("topic", "")
    assert "руководств" in topic.lower() or "эксплуатац" in topic.lower(), (
        f"topic={topic!r}"
    )


def test_answer_no_params(intent_router):
    router, _ = intent_router
    decision = router.route("привет")
    assert decision.intent.name == "answer", (
        f"intent={decision.intent.name}"
    )
    assert decision.intent.params == {}


# ---------------------------------------------------------------------------
# 2. Прямой вызов _extract_params — без исключений
# ---------------------------------------------------------------------------

def test_extract_params_unpacks_four_values(intent_router):
    """
    ParameterRouter.extract_params возвращает 4 значения
    (params, accepted, rejected, debug). Проверяем, что
    IntentRouter._extract_params корректно распаковывает их.
    """
    router, _ = intent_router
    params = router._extract_params(
        "открой презентации итоговые занятия",
        "open_presentation",
    )
    assert isinstance(params, dict)
    assert params.get("topic") == "итоговые занятия"


def test_extract_params_for_answer(intent_router):
    router, _ = intent_router
    params = router._extract_params("привет", "answer")
    assert params == {}


def run_all():
    print("Запуск через pytest: "
          "pytest -v tools/test_intent_router_parameter_integration.py",
          flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(run_all())
