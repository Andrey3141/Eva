"""
Semantic-классификатор Intent через embeddings.

Эталоны берутся из датасета (intent → примеры). Запрос эмбеддится
в роли "query", эталоны — в роли "passage". Сравнение — cosine
(L2-нормализованные вектора → скалярное произведение).

Возвращает top-1 intent с confidence = max similarity.
"""
from __future__ import annotations

from typing import Optional

import numpy as np

from .providers import EmbeddingProvider
from .types import IntentPrediction


class EmbeddingRouter:
    def __init__(
        self,
        examples: dict[str, list[str]],
        provider: EmbeddingProvider,
        min_score: float = 0.5,
    ):
        """
        examples: intent → list[str] эталонных фраз.
        provider: EmbeddingProvider (query/passage роли).
        min_score: порог, ниже которого intent считается пустым
                   (confidence = 0, intent = "").
        """
        self._provider = provider
        self._examples = dict(examples or {})
        self._min_score = float(min_score)
        self._intents: list[str] = []
        self._ref_matrix: Optional[np.ndarray] = None
        self._built = False

    # ------------------------------------------------------------------
    def _build(self) -> None:
        if self._built:
            return
        self._built = True

        all_texts: list[str] = []
        all_intents: list[str] = []
        for intent, phrases in self._examples.items():
            for p in phrases:
                all_texts.append(p)
                all_intents.append(intent)

        if not all_texts:
            self._intents = []
            self._ref_matrix = None
            return

        vectors = self._provider.embed(all_texts, role="passage")
        if not vectors:
            self._intents = []
            self._ref_matrix = None
            return

        self._intents = all_intents
        self._ref_matrix = np.asarray(vectors, dtype="float32")

    # ------------------------------------------------------------------
    def predict(self, text: str) -> IntentPrediction:
        if not text or not text.strip():
            return IntentPrediction(intent="", confidence=0.0, source="embedding")

        self._build()
        if self._ref_matrix is None or not self._intents:
            return IntentPrediction(intent="", confidence=0.0, source="embedding")

        try:
            q = self._provider.embed([text], role="query")
        except Exception:
            return IntentPrediction(intent="", confidence=0.0, source="embedding")

        if not q:
            return IntentPrediction(intent="", confidence=0.0, source="embedding")

        qv = np.asarray(q[0], dtype="float32")
        if qv.size != self._ref_matrix.shape[1]:
            # Провайдер вернул другую размерность — не гадаем.
            return IntentPrediction(intent="", confidence=0.0, source="embedding")

        sims = self._ref_matrix @ qv  # обе стороны L2-нормализованы

        if sims.size == 0:
            return IntentPrediction(intent="", confidence=0.0, source="embedding")

        best_idx = int(np.argmax(sims))
        best_score = float(sims[best_idx])

        if best_score < self._min_score:
            return IntentPrediction(
                intent="",
                confidence=best_score,
                source="embedding",
            )

        return IntentPrediction(
            intent=self._intents[best_idx],
            confidence=best_score,
            source="embedding",
        )
