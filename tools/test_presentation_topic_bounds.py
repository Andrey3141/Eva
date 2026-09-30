"""
Regression-тесты границ topic для open_presentation.

Фиксируют:
  - корректное извлечение topic без захвата "презентацию" / "и";
  - проблемный случай, где ParameterRouter сейчас может ошибиться.

Запуск:
    pytest -v tools/test_presentation_topic_bounds.py
    pytest -v tools/test_presentation_topic_bounds.py -s
"""
import sys
from unittest import mock

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
                   ("тем", "занят", "токов", "трансформатор", "электр",
                    "физик", "охране", "труда", "монтаж", "защит",
                    "безопас", "материал", "правил", "итогов")):
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
        debug=True,
    )
    fusion = ParameterFusion(min_ml=0.30, min_emb=0.30, agree_bonus=0.10)
    return ParameterRouter(ml, emb, fusion)


def _extract(router, text, intent_name="open_presentation"):
    intent = Intent(name=intent_name, params={}, confidence=0.9, raw_text=text)
    return router.extract(text, intent)


# ---------------------------------------------------------------------------
# Корректный случай
# ---------------------------------------------------------------------------

def test_presentation_topic_bez_lischnih_slov(router):
    """
    "открой презентацию итоговое занятие" → topic = "итоговое занятие".
    Не должно захватывать "презентацию".
    """
    res = _extract(router, "открой презентацию итоговое занятие")
    topic = res.params.get("topic", "")
    assert topic, f"topic отсутствует, params={res.params}, debug={res.debug}"
    assert "презентац" not in topic.lower(), (
        f"'презентацию' не должно быть в topic: topic={topic!r}"
    )
    assert "итогов" in topic.lower(), (
        f"topic должен содержать 'итогов': topic={topic!r}"
    )


# ---------------------------------------------------------------------------
# Проблемный случай: "и" между презентацией и темой
# ---------------------------------------------------------------------------

def test_presentation_topic_no_leading_i(router):
    """
    ПРОБЛЕМА: "открой презентацию и токовые занятия".
    Текущий ParameterRouter может включить в topic "презентацию" / "и".
    Ожидаемое поведение: topic = "токовые занятия" (или близкое).
    """
    res = _extract(router, "открой презентацию и токовые занятия")
    topic = res.params.get("topic", "")
    assert topic, f"topic отсутствует, params={res.params}, debug={res.debug}"
    assert "презентац" not in topic.lower(), (
        f"'презентацию' не должно быть в topic: topic={topic!r}"
    )
    assert not topic.lower().startswith("и "), (
        f"topic не должен начинаться с 'и': topic={topic!r}"
    )
    assert "токов" in topic.lower(), (
        f"topic должен содержать 'токов': topic={topic!r}"
    )


def test_presentation_topic_does_not_start_with_glue(router):
    """
    Topic не должен начинаться с предлогов/союзов: "и", "а", "но".
    """
    for text in (
        "открой презентацию и токовые занятия",
        "покажи презентацию а также про трансформаторы",
    ):
        res = _extract(router, text)
        topic = res.params.get("topic", "")
        if not topic:
            continue
        first = topic.split()[0].lower() if topic.split() else ""
        assert first not in ("и", "а", "но", "или"), (
            f"topic начинается со служебного {first!r}: topic={topic!r}"
        )


def run_all():
    print("Запуск через pytest: "
          "pytest -v tools/test_presentation_topic_bounds.py -s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(run_all())
