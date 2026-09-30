"""
Тесты EmbeddingCandidateScorer.

Контракт:
  scorer отвечает на вопрос "насколько кандидат семантически похож
  на значение роли". Он не выполняет typed validation — это Fusion.

FakeEmbeddingProvider:
  semantic-оси для известных категорий; fallback-ось ортогональна
  всем semantic-осям, поэтому неизвестные значения (числа, служебные)
  имеют similarity ≈ 0 со всеми сигнатурами ролей.
"""
import sys

import numpy as np
import pytest

from assistant.intent.parameter.candidate_generator import (
    generate_span_candidates,
)
from assistant.intent.parameter.embedding_candidate_scorer import (
    EmbeddingCandidateScorer,
)
from assistant.intent.parameter.roles import Role


class FakeEmbeddingProvider:
    """
    Детерминированный fake.

    Semantic-оси:
      0: topic
      1: student
      2: grade-words (оценка, балл, отметка)
      3: command
      4: object

    Fallback-ось 5: всё остальное (числа, неизвестное).
    Ось 5 ортогональна осям 0..4, поэтому cosine с сигнатурами ролей ≈ 0.
    """
    def __init__(self, dim=8):
        self._dim = dim

    def embed(self, texts, role="passage"):
        out = []
        for t in texts:
            low = (t or "").strip().lower()
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

            # Если ничего не сматчилось — fallback-ось, ортогональная всем.
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


@pytest.fixture
def scorer():
    return EmbeddingCandidateScorer(
        provider=FakeEmbeddingProvider(),
        max_span_tokens=5,
        top_k=5,
        extra_candidates=3,
    )


# ---------------------------------------------------------------------------
# 0. Генератор кандидатов
# ---------------------------------------------------------------------------

def test_numeric_span_is_generated():
    candidates = generate_span_candidates(
        "поставь Иванову оценку 8",
        max_len=5,
    )
    values = [c.value for c in candidates]
    assert "8" in values, f"Генератор не создал '8': {values}"


# ---------------------------------------------------------------------------
# 1. Семантическая близость кандидатов
# ---------------------------------------------------------------------------

def test_student_candidate_scores_high(scorer):
    results = scorer.score_role("Иванову", Role.STUDENT)
    assert results, "Нет кандидатов для STUDENT"
    assert results[0].value.lower() == "иванову"
    assert results[0].confidence > 0.5


def test_topic_candidate_scores_high(scorer):
    results = scorer.score_role("трансформаторы", Role.TOPIC)
    assert results, "Нет кандидатов для TOPIC"
    assert "трансформатор" in results[0].value.lower()
    assert results[0].confidence > 0.5


def test_numeric_candidate_low_semantic(scorer):
    results = scorer.score_role("8", Role.GRADE)
    assert results, "Числовой кандидат должен проходить структурный фильтр"
    by_val = {r.value.lower(): r.confidence for r in results}
    assert "8" in by_val
    assert by_val["8"] < 0.5


# ---------------------------------------------------------------------------
# 2. Служебные слова не становятся кандидатами ролей
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("word", ["поставь", "открой", "покажи", "запусти"])
def test_command_words_not_in_student(scorer, word):
    results = scorer.score_role(word, Role.STUDENT)
    values = [r.value.lower() for r in results]
    assert word not in values


@pytest.mark.parametrize("word", ["презентацию", "видео", "ролик"])
def test_object_words_not_in_student(scorer, word):
    results = scorer.score_role(word, Role.STUDENT)
    values = [r.value.lower() for r in results]
    assert word not in values


@pytest.mark.parametrize("word", ["про", "по", "о", "об", "на", "тему"])
def test_topic_markers_not_in_topic(scorer, word):
    results = scorer.score_role(word, Role.TOPIC)
    values = [r.value.lower() for r in results]
    assert word not in values


# ---------------------------------------------------------------------------
# 3. Fake: числовой кандидат не попадает в STUDENT/TOPIC
# ---------------------------------------------------------------------------

def test_numeric_candidate_not_student(scorer):
    results = scorer.score_role("Иванову 8", Role.STUDENT)
    values = [r.value.lower() for r in results]
    assert "иванову" in values, f"student candidates: {values}"
    assert "8" not in values, (
        f"Одиночное число не должно быть STUDENT-кандидатом: {values}"
    )


def test_numeric_candidate_not_topic(scorer):
    results = scorer.score_role("презентацию 8", Role.TOPIC)
    values = [r.value.lower() for r in results]
    assert "8" not in values, (
        f"Одиночное число не должно быть TOPIC-кандидатом: {values}"
    )


def test_numeric_candidate_low_similarity_to_all_roles(scorer):
    """
    "8" должен иметь similarity ≈ 0 со всеми ролями, кроме разве что
    некоторого низкого значения для GRADE.
    """
    for role in (Role.STUDENT, Role.TOPIC, Role.COMMAND, Role.OBJECT):
        results = scorer.score_role("8", role)
        by_val = {r.value.lower(): r.confidence for r in results}
        assert by_val.get("8", 0.0) < 0.3, (
            f"'8' не должен иметь высокий score для роли {role}: {by_val}"
        )


# ---------------------------------------------------------------------------
# 4. Regression: числовой кандидат выживает после scoring
# ---------------------------------------------------------------------------

def test_numeric_candidate_survives_embedding_scoring(scorer):
    results = scorer.score_role(
        "поставь Иванову оценку 8",
        Role.GRADE,
    )
    values = [r.value.lower() for r in results]
    assert "8" in values, (
        f"Числовой кандидат '8' потерялся после scoring: {values}"
    )
    assert "оценку" in values, (
        f"Слово 'оценку' должно присутствовать в GRADE-кандидатах: {values}"
    )


def test_grade_semantically_higher_than_number(scorer):
    results = scorer.score_role(
        "поставь Иванову оценку 8",
        Role.GRADE,
    )
    by_val = {r.value.lower(): r.confidence for r in results}
    assert by_val.get("оценку", 0.0) > by_val.get("8", 0.0), (
        f"Ожидалось 'оценку' > '8' по semantic score: {by_val}"
    )


# ---------------------------------------------------------------------------
# 5. Реальные фразы
# ---------------------------------------------------------------------------

def test_real_phrase_grade_8_has_both_candidates(scorer):
    text = "поставь Иванову оценку 8"

    student = scorer.score_role(text, Role.STUDENT)
    student_values = [r.value.lower() for r in student]
    assert "иванову" in student_values

    grade = scorer.score_role(text, Role.GRADE)
    grade_values = [r.value.lower() for r in grade]
    assert "оценку" in grade_values
    assert "8" in grade_values


def test_real_phrase_grade_reordered(scorer):
    text = "Иванову поставь 8"

    student = scorer.score_role(text, Role.STUDENT)
    student_values = [r.value.lower() for r in student]
    assert "иванову" in student_values

    grade = scorer.score_role(text, Role.GRADE)
    grade_values = [r.value.lower() for r in grade]
    assert "8" in grade_values


def test_real_phrase_grade_word(scorer):
    text = "выставь Иванову восемь"

    student = scorer.score_role(text, Role.STUDENT)
    student_values = [r.value.lower() for r in student]
    assert "иванову" in student_values

    grade = scorer.score_role(text, Role.GRADE)
    grade_values = [r.value.lower() for r in grade]
    assert "восемь" in grade_values


def test_real_phrase_topic(scorer):
    text = "открой презентацию про трансформаторы"
    topic = scorer.score_role(text, Role.TOPIC)
    topic_values = [r.value.lower() for r in topic]
    assert any("трансформатор" in v for v in topic_values)
    assert "про" not in topic_values


def run_all():
    print("Запуск через pytest: "
          "pytest -v tools/test_embedding_candidate_scorer.py", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(run_all())
