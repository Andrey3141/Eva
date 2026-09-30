"""
Тесты EmbeddingRouter с детерминированным fake-провайдером.
Без fastembed, без сети.
"""
import math

import numpy as np
import pytest

from assistant.intent.router.embedding_router import EmbeddingRouter
from assistant.intent.router.providers import EmbeddingProvider


class FakeEmbeddingProvider(EmbeddingProvider):
    """
    Детерминированный провайдер: кладёт фразы в фиксированные кластеры
    по ключевым словам. Нужен для проверки логики Router, не для семантики.
    """

    def __init__(self, dim: int = 8):
        self._dim = dim
        # Несколько "осей" для кластеров.
        self._axes = {
            "video":        [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "presentation": [0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "grade":        [0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "next":         [0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0],
            "answer":       [0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0],
        }

    def embed(self, texts, role="passage"):
        out = []
        for t in texts:
            low = (t or "").lower()
            vec = np.zeros(self._dim, dtype="float32")
            for key, axis in self._axes.items():
                if key in low:
                    vec += np.asarray(axis, dtype="float32")
            if not vec.any():
                vec = np.asarray(self._axes["answer"], dtype="float32")
            n = float(np.linalg.norm(vec))
            if n > 0:
                vec = vec / n
            out.append(vec.tolist())
        return out

    @property
    def dimension(self):
        return self._dim


@pytest.fixture
def examples():
    return {
        "open_video": ["включи видео", "покажи видео"],
        "open_presentation": ["открой презентацию", "покажи слайды"],
        "grade_student": ["поставь Иванову четыре", "Иванов пять"],
        "next_slide": ["следующий слайд", "дальше"],
        "answer": ["привет", "как дела"],
    }


def test_predict_returns_top_intent(examples):
    router = EmbeddingRouter(examples, FakeEmbeddingProvider(), min_score=0.3)
    pred = router.predict("включи видео")
    assert pred.intent == "open_video"
    assert pred.confidence > 0.0
    assert pred.source == "embedding"


def test_predict_empty_text():
    router = EmbeddingRouter({"answer": ["x"]}, FakeEmbeddingProvider(), min_score=0.3)
    pred = router.predict("")
    assert pred.intent == ""
    assert pred.confidence == 0.0


def test_predict_below_min_score():
    router = EmbeddingRouter({"open_video": ["video"]}, FakeEmbeddingProvider(), min_score=0.99)
    pred = router.predict("нечто непонятное")
    assert pred.intent == ""


def test_predict_no_examples():
    router = EmbeddingRouter({}, FakeEmbeddingProvider(), min_score=0.3)
    pred = router.predict("включи видео")
    assert pred.intent == ""
    assert pred.confidence == 0.0


def test_embedding_router_uses_passage_and_query_roles():
    """
    Проверяем, что Router передаёт role="passage" для эталонов
    и role="query" для запроса.
    """
    calls = {"passage": 0, "query": 0}

    class RoleTracker(EmbeddingProvider):
        def __init__(self):
            self._inner = FakeEmbeddingProvider()
        def embed(self, texts, role="passage"):
            calls[role] = calls.get(role, 0) + 1
            return self._inner.embed(texts, role=role)
        @property
        def dimension(self):
            return self._inner.dimension

    router = EmbeddingRouter({"open_video": ["включи видео"]},
                             RoleTracker(), min_score=0.3)
    router.predict("включи видео")

    assert calls["passage"] == 1
    assert calls["query"] == 1
