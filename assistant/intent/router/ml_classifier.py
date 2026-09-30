"""
Локальный ML-классификатор Intent.

Стек: TF-IDF (char_wb 2..4) + LogisticRegression (sklearn).
Без PyTorch, без нейросетей. Быстро на CPU, хорошо для русского
(символьные n-граммы не требуют токенизации).

Если sklearn не установлен или обучающих примеров нет —
predict() возвращает пустое предсказание (confidence=0).
"""
from __future__ import annotations

from typing import Optional

from .types import IntentPrediction


class MLIntentClassifier:
    def __init__(
        self,
        examples: dict[str, list[str]],
        min_confidence: float = 0.4,
    ):
        self._examples = dict(examples or {})
        self._min_confidence = float(min_confidence)
        self._pipeline = None
        self._classes: list[str] = []
        self._built = False

    # ------------------------------------------------------------------
    def _build(self) -> None:
        if self._built:
            return
        self._built = True

        texts: list[str] = []
        labels: list[str] = []
        for intent, phrases in self._examples.items():
            for p in phrases:
                texts.append(p)
                labels.append(intent)

        if len(texts) < 2 or len(set(labels)) < 2:
            self._pipeline = None
            self._classes = []
            return

        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.linear_model import LogisticRegression
            from sklearn.pipeline import Pipeline
        except Exception:
            self._pipeline = None
            self._classes = []
            return

        pipeline = Pipeline([
            ("tfidf", TfidfVectorizer(
                analyzer="char_wb",
                ngram_range=(2, 4),
                min_df=1,
                lowercase=True,
            )),
            ("clf", LogisticRegression(
                max_iter=500,
            )),
        ])

        try:
            pipeline.fit(texts, labels)
        except Exception:
            self._pipeline = None
            self._classes = []
            return

        self._pipeline = pipeline
        self._classes = list(pipeline.named_steps["clf"].classes_)

    # ------------------------------------------------------------------
    def predict(self, text: str) -> IntentPrediction:
        if not text or not text.strip():
            return IntentPrediction(intent="", confidence=0.0, source="ml")

        self._build()
        if self._pipeline is None:
            return IntentPrediction(intent="", confidence=0.0, source="ml")

        try:
            proba = self._pipeline.predict_proba([text])[0]
        except Exception:
            return IntentPrediction(intent="", confidence=0.0, source="ml")

        if len(proba) == 0:
            return IntentPrediction(intent="", confidence=0.0, source="ml")

        best_idx = int(max(range(len(proba)), key=lambda i: proba[i]))
        best_conf = float(proba[best_idx])
        best_intent = self._classes[best_idx]

        if best_conf < self._min_confidence:
            return IntentPrediction(
                intent="",
                confidence=best_conf,
                source="ml",
            )

        return IntentPrediction(
            intent=best_intent,
            confidence=best_conf,
            source="ml",
        )
