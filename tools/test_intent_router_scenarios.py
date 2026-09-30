"""
Сценарии каскадного IntentRouter, которые раньше проверялись
на EchoIntentParser, + проверка извлечения params + диагностика
спорных фраз.

  - "сколько будет 2 плюс 2"  → answer, без grade-параметров
  - "два плюс два"            → answer
  - "открой презентацию по физике"    → open_presentation + topic
  - "включи видео про электричество"  → open_video + topic
  - "поставь Иванову четыре"          → grade_student + student/grade
  - "следующий слайд"                 → next_slide, без params
  - "покажи слайды по X"              → open_presentation + topic

Extraction выполняется локально через ParameterExtractor,
LLM не вызывается.
"""
import os
import sys

import numpy as np
import pytest

from assistant.intent.router.embedding_router import EmbeddingRouter
from assistant.intent.router.fusion import IntentFusion
from assistant.intent.router.llm_router import LLMIntentRouter
from assistant.intent.router.ml_classifier import MLIntentClassifier
from assistant.intent.router.router import IntentRouter


class FakeEmbeddingProvider:
    """
    Детерминированный fake.

    Порядок проверок важен:
      1. video — если есть "видео"/"ролик"/"видеозапис".
      2. next_slide — если есть "следующ"/"дальше"/"переключи слайд".
      3. presentation — если есть "презентац"/"слайд".
      4. grade — фамилии.
      5. math/answer — математические маркеры.
      6. greeting.

    Неизвестный текст → нулевой вектор.
    """

    def __init__(self, dim=8):
        self._dim = dim

    def embed(self, texts, role="passage"):
        out = []
        for t in texts:
            low = (t or "").lower()
            v = np.zeros(self._dim, dtype="float32")

            if "видео" in low or "ролик" in low or "видеозапис" in low:
                v[0] = 1.0
            elif ("следующ" in low
                  or "дальше" in low
                  or "переключи слайд" in low):
                v[3] = 1.0
            elif "презентац" in low or "слайд" in low:
                v[1] = 1.0
            elif any(s in low for s in ("иванов", "сидоров", "петров", "смирнов")):
                v[2] = 1.0
            elif any(w in low for w in ("плюс", "минус", "умножить", "сколько", "раздел")):
                v[4] = 1.0
            elif any(w in low for w in ("привет", "как дела", "здравствуй")):
                v[5] = 1.0
            # else: нулевой

            n = float(np.linalg.norm(v))
            if n > 0:
                v = v / n
            out.append(v.tolist())
        return out

    @property
    def dimension(self):
        return self._dim


class FakeLLM:
    def __init__(self):
        self.calls = 0

    def chat(self, user_message, system_prompt=None):
        self.calls += 1
        return '{"intent": "unknown", "confidence": 0.1, "params": {}}'

    def name(self):
        return "fake"


EXAMPLES = {
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


def _make_router(threshold=0.6):
    llm = FakeLLM()
    router = IntentRouter(
        embedding_router=EmbeddingRouter(EXAMPLES, FakeEmbeddingProvider(),
                                         min_score=0.3),
        ml_classifier=MLIntentClassifier(EXAMPLES, min_confidence=0.1),
        fusion=IntentFusion(min_individual=0.5, agree_bonus=0.05),
        llm_router=LLMIntentRouter(llm),
        confidence_threshold=threshold,
    )
    return router, llm


# ---------------------------------------------------------------------------
# Классификация — старые сценарии
# ---------------------------------------------------------------------------

def test_math_2_plus_2_not_grade_student():
    router, llm = _make_router()
    decision = router.route("сколько будет 2 плюс 2")
    assert decision.intent.name != "grade_student"
    assert decision.intent.name == "answer"


def test_math_word_only_not_grade_student():
    router, llm = _make_router()
    decision = router.route("два плюс два")
    assert decision.intent.name != "grade_student"
    assert decision.intent.name == "answer"


def test_open_presentation_phrase():
    router, llm = _make_router()
    decision = router.route("открой презентацию по физике")
    assert decision.intent.name == "open_presentation"


def test_open_video_phrase():
    router, llm = _make_router()
    decision = router.route("включи видео про электричество")
    assert decision.intent.name == "open_video"


def test_scenarios_do_not_call_llm():
    router, llm = _make_router()

    router.route("сколько будет 2 плюс 2")
    router.route("два плюс два")
    router.route("открой презентацию по физике")
    router.route("включи видео про электричество")

    assert llm.calls == 0, (
        f"LLM был вызван {llm.calls} раз(а) — локальный каскад "
        f"должен был справиться сам."
    )


# ---------------------------------------------------------------------------
# Extraction: params заполняются локально
# ---------------------------------------------------------------------------

def test_open_video_extracts_topic_locally():
    router, llm = _make_router()
    decision = router.route("включи видео про электричество")
    assert decision.intent.name == "open_video"
    assert decision.intent.params.get("topic") == "электричество"
    assert llm.calls == 0


def test_open_presentation_extracts_topic_locally():
    router, llm = _make_router()
    decision = router.route("открой презентацию по физике")
    assert decision.intent.name == "open_presentation"
    assert decision.intent.params.get("topic") == "физике"
    assert llm.calls == 0


def test_grade_student_extracts_params_locally():
    router, llm = _make_router()
    decision = router.route("поставь Иванову четыре")
    assert decision.intent.name == "grade_student"
    assert decision.intent.params.get("student") == "Иванову"
    assert decision.intent.params.get("grade") == 4
    assert llm.calls == 0


def test_next_slide_empty_params():
    router, llm = _make_router()
    decision = router.route("следующий слайд")
    assert decision.intent.name == "next_slide", decision.intent.name
    assert decision.intent.params == {}


def test_answer_empty_params():
    router, llm = _make_router()
    decision = router.route("привет")
    assert decision.intent.name == "answer"
    assert decision.intent.params == {}


def test_math_does_not_get_grade_params():
    router, llm = _make_router()
    decision = router.route("сколько будет 2 плюс 2")
    assert decision.intent.name == "answer"
    assert "student" not in decision.intent.params
    assert "grade" not in decision.intent.params


# ---------------------------------------------------------------------------
# Диагностика спорных фраз next_slide vs open_presentation
# ---------------------------------------------------------------------------

def test_diagnose_next_slide_vs_presentation(capsys):
    """
    Диагностический + контрактный тест.

    Показывает реальные предсказания embedding/ML/fusion для фраз,
    которые легко спутать, и фиксирует:
      - "следующий слайд" → next_slide
      - "дальше"          → next_slide
      - "открой слайды"   → open_presentation
      - "покажи слайды"   → open_presentation
    """
    router, llm = _make_router()

    for text in ("следующий слайд", "дальше", "открой слайды", "покажи слайды"):
        emb = router._emb.predict(text)
        ml = router._ml.predict(text)
        fused = router._fusion.fuse(emb, ml)
        print(f"{text!r}", flush=True)
        print(f"  embedding: intent={emb.intent!r} conf={emb.confidence:.2f}",
              flush=True)
        print(f"  ml:        intent={ml.intent!r} conf={ml.confidence:.2f}",
              flush=True)
        print(f"  fusion:    intent={fused.intent!r} conf={fused.confidence:.2f} "
              f"agree={fused.agree}", flush=True)

    d1 = router.route("следующий слайд")
    assert d1.intent.name == "next_slide", (
        f"'следующий слайд' ошибочно распознан как {d1.intent.name}"
    )

    d2 = router.route("дальше")
    assert d2.intent.name == "next_slide", (
        f"'дальше' ошибочно распознан как {d2.intent.name}"
    )

    d3 = router.route("открой слайды")
    assert d3.intent.name == "open_presentation", (
        f"'открой слайды' ошибочно распознан как {d3.intent.name}"
    )

    d4 = router.route("покажи слайды")
    assert d4.intent.name == "open_presentation", (
        f"'покажи слайды' ошибочно распознан как {d4.intent.name}"
    )


# ---------------------------------------------------------------------------
# Прямой запуск
# ---------------------------------------------------------------------------

def _run_all():
    tests = [
        test_math_2_plus_2_not_grade_student,
        test_math_word_only_not_grade_student,
        test_open_presentation_phrase,
        test_open_video_phrase,
        test_scenarios_do_not_call_llm,
        test_open_video_extracts_topic_locally,
        test_open_presentation_extracts_topic_locally,
        test_grade_student_extracts_params_locally,
        test_next_slide_empty_params,
        test_answer_empty_params,
        test_math_does_not_get_grade_params,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"[OK] {t.__name__}", flush=True)
        except AssertionError as e:
            failed += 1
            print(f"[FAIL] {t.__name__}: {e}", flush=True)
        except Exception as e:
            failed += 1
            print(f"[ERROR] {t.__name__}: {type(e).__name__}: {e}", flush=True)
    print(flush=True)
    print(f"=== {len(tests) - failed}/{len(tests)} SCENARIO TESTS PASSED ===", flush=True)
    return failed


def main():
    if not os.path.exists("assistant"):
        print("Запускать из корня проекта.", flush=True)
        sys.exit(2)
    sys.exit(1 if _run_all() else 0)


if __name__ == "__main__":
    main()
