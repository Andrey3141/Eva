"""
Тесты ParameterRouter: ML и Embedding дают независимые кандидаты,
Fusion принимает решение с учётом typed-валидатора.

Проверяют:
  - open_presentation: topic в разных формулировках;
  - open_video: topic;
  - grade_student: student + grade (Fusion принимает typed-valid
    значение независимо от semantic score);
  - next_slide / answer — нет params;
  - отрицательные случаи для grade;
  - ML и Embedding работают независимо (debug.ml_spans и debug.emb_candidates).

Используют FakeEmbeddingProvider, чтобы не зависеть от fastembed.
"""
import sys

import numpy as np
import pytest

from assistant.intent.base import Intent
from assistant.intent.parameter import (
    MLSlotTagger, EmbeddingCandidateScorer, ParameterFusion, ParameterRouter,
    load_parameter_examples,
)


class FakeEmbeddingProvider:
    """Детерминированный fake: семантические оси по ключевым словам."""
    def __init__(self, dim=16):
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
                    "материал", "правил")):
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


@pytest.fixture(scope="module")
def examples():
    return load_parameter_examples()


@pytest.fixture
def router(examples):
    ml = MLSlotTagger(examples, min_confidence=0.10)
    emb = EmbeddingCandidateScorer(
        provider=FakeEmbeddingProvider(),
        max_span_tokens=5,
        top_k=5,
        extra_candidates=3,
    )
    fusion = ParameterFusion(min_ml=0.30, min_emb=0.30, agree_bonus=0.10)
    return ParameterRouter(ml, emb, fusion)


def _extract(router, text, intent_name):
    intent = Intent(name=intent_name, params={}, confidence=0.9, raw_text=text)
    return router.extract(text, intent)


# ---------------------------------------------------------------------------
# open_presentation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text,expected_root", [
    ("открой презентацию итоговые занятия", "занят"),
    ("открой презентацию итоговое занятие", "занят"),
    ("открой презентацию про итоговые занятия", "занят"),
    ("открой презентацию на тему итоговых занятий", "занят"),
    ("покажи презентацию итоговые занятия", "занят"),
    ("запусти презентацию по итоговым занятиям", "занят"),
    ("покажи презентацию по электромонтажу", "электромонтаж"),
    ("открой слайды по правилам безопасности", "безопас"),
    ("покажи материал по охране труда", "охране"),
])
def test_open_presentation_topic(router, text, expected_root):
    res = _extract(router, text, "open_presentation")
    assert "topic" in res.params, f"params={res.params}, debug={res.debug}"
    assert expected_root in res.params["topic"].lower(), \
        f"topic={res.params['topic']!r}"


# ---------------------------------------------------------------------------
# open_video
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "открой видео трансформаторы",
    "открой видео про трансформаторы",
    "покажи видео про трансформаторы",
    "запусти ролик трансформаторы",
    "открой ролик про силовые трансформаторы",
])
def test_open_video_topic(router, text):
    res = _extract(router, text, "open_video")
    assert "topic" in res.params, f"params={res.params}, debug={res.debug}"
    assert "трансформатор" in res.params["topic"].lower()


# ---------------------------------------------------------------------------
# grade_student — Fusion принимает typed-valid значение
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text, expected_grade", [
    ("поставь Иванову 8", 8),
    ("поставь Иванову оценку 8", 8),
    ("Иванову поставь 8", 8),
    ("выставь Иванову восемь", 8),
])
def test_grade_fusion_accepts_typed_valid_value(router, text, expected_grade):
    """
    Число/числительное должно приниматься Fusion, даже если
    embedding даёт ему низкий semantic score, а словам типа "оценку" —
    высокий. Решение принимает typed-валидатор.
    """
    res = _extract(router, text, "grade_student")
    assert res.params.get("grade") == expected_grade, (
        f"params={res.params}, debug={res.debug}"
    )


def test_grade_fusion_rejects_semantic_wrapper(router):
    """
    "оценку" и "оценку 8" семантически похожи на GRADE,
    но typed-валидатор их отвергает. Финальный grade = 8.
    """
    res = _extract(router, "поставь Иванову оценку 8", "grade_student")
    grade_val = res.params.get("grade")
    assert grade_val is not None, f"params={res.params}"
    assert grade_val == 8, f"params={res.params}"
    assert grade_val != "оценку"
    assert grade_val != "оценку 8"


def test_grade_student_params(router):
    """
    Проверяет и student, и grade для фразы "поставь Иванову оценку 8".
    """
    res = _extract(router, "поставь Иванову оценку 8", "grade_student")
    assert "student" in res.params, f"params={res.params}, debug={res.debug}"
    assert "grade" in res.params, f"params={res.params}, debug={res.debug}"
    assert "иванов" in res.params["student"].lower()
    assert res.params["grade"] == 8


# ---------------------------------------------------------------------------
# Нет параметров
# ---------------------------------------------------------------------------

def test_next_slide_no_params(router):
    res = _extract(router, "следующий слайд", "next_slide")
    assert res.params == {}


def test_answer_no_params(router):
    res = _extract(router, "сколько будет два плюс два", "answer")
    assert res.params == {}


# ---------------------------------------------------------------------------
# Отрицательные: число как часть обычного текста
# ---------------------------------------------------------------------------

def test_grade_not_from_math(router):
    res = _extract(router, "сколько будет 2 плюс 2", "grade_student")
    assert "grade" not in res.params, f"params={res.params}"


# ---------------------------------------------------------------------------
# Независимость ML и Embedding
# ---------------------------------------------------------------------------

def test_ml_and_embedding_independent(router):
    """
    ML и Embedding реально дают СВОИ кандидаты, а не Embedding просто
    проверяет ML-результат.
    """
    res = _extract(router, "открой презентацию итоговые занятия",
                   "open_presentation")
    debug = res.debug

    assert debug.get("ml_spans"), "ML не дал кандидатов"

    emb_for_topic = debug.get("emb_candidates", {}).get("topic", [])
    assert len(emb_for_topic) >= 2, \
        f"Embedding должен дать несколько кандидатов: {emb_for_topic}"

    ml_values = {m["value"] for m in debug["ml_spans"] if m["role"] == "TOPIC"}
    emb_values = {e["value"] for e in emb_for_topic}
    assert emb_values - ml_values, \
        f"Embedding должен предлагать свои варианты, отличные от ML. " \
        f"ml={ml_values}, emb={emb_values}"


def run_all():
    print("Запуск через pytest: pytest -v tools/test_parameter_router.py",
          flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(run_all())
