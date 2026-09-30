"""
Regression-тесты grade_student в ParameterRouter.

Фиксируют корректное извлечение student + grade для базовых команд:

    "поставь Иванову 2"       → student="Иванову", grade=2
    "поставь Иванову два"     → student="Иванову", grade=2
    "поставь Иванову два балла" → student="Иванову", grade=2
    "Иванову 2"               → student="Иванову", grade=2

Плюс другие фамилии, чтобы не завязываться на "Иванову".

Запуск:
    pytest -v tools/test_grade_student_parameter_router.py -s
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
    """Оси: topic / student / grade / command / object / fallback."""
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
                    "материал", "правил", "итогов")):
                v[0] = 1.0
                matched = True
            if any(w in low for w in
                   ("фамил", "ученик", "студент", "фио",
                    "иванов", "сидоров", "петров", "смирнов",
                    "кузнецов", "морозов", "волков")):
                v[1] = 1.0
                matched = True
            if any(w in low for w in ("оценк", "балл", "отметк")):
                v[2] = 1.0
                matched = True
            if any(w in low for w in
                   ("команд", "приказ", "действ",
                    "открой", "покажи", "запусти", "включи",
                    "поставь", "выставь", "воспроизведи", "дай", "вкати")):
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
        debug=True,
    )
    fusion = ParameterFusion(min_ml=0.30, min_emb=0.30, agree_bonus=0.10)
    return ParameterRouter(ml, emb, fusion)


def _extract(router, text):
    intent = Intent(name="grade_student", params={},
                    confidence=0.9, raw_text=text)
    return router.extract(text, intent)


# ---------------------------------------------------------------------------
# 1. Базовые команды с "Иванову"
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "поставь Иванову 2",
    "поставь Иванову два",
    "поставь Иванову два балла",
    "Иванову 2",
])
def test_grade_ivanovu_2(router, text):
    res = _extract(router, text)
    assert res.params.get("student") == "Иванову", (
        f"student={res.params.get('student')!r}, "
        f"params={res.params}, debug={res.debug}"
    )
    assert res.params.get("grade") == 2, (
        f"grade={res.params.get('grade')!r}, "
        f"params={res.params}, debug={res.debug}"
    )


# ---------------------------------------------------------------------------
# 2. Другие фамилии — чтобы не завязаться на одну строку
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text,expected_student", [
    ("поставь Сидорову 2", "Сидорову"),
    ("поставь Петрову два", "Петрову"),
    ("Кузнецову 2", "Кузнецову"),
    ("Морозову два балла", "Морозову"),
])
def test_grade_other_students(router, text, expected_student):
    res = _extract(router, text)
    student = res.params.get("student", "")
    assert student, (
        f"student отсутствует, params={res.params}, debug={res.debug}"
    )
    assert expected_student.lower() in student.lower(), (
        f"student={student!r} не содержит {expected_student!r}"
    )
    assert res.params.get("grade") == 2, (
        f"grade={res.params.get('grade')!r}"
    )


# ---------------------------------------------------------------------------
# 3. Служебные слова не становятся student
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "поставь Иванову 2",
    "поставь Иванову два",
    "поставь Иванову два балла",
    "Иванову 2",
])
def test_service_words_not_student(router, text):
    res = _extract(router, text)
    student = res.params.get("student", "").lower()
    for bad in ("поставь", "оценку", "балла", "балл", "два", "2"):
        assert bad not in student, (
            f"student={student!r} содержит служебное {bad!r}"
        )


def run_all():
    print("Запуск через pytest: "
          "pytest -v tools/test_grade_student_parameter_router.py -s",
          flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(run_all())
