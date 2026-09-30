"""
MLSlotTagger — token classification + span grouping.

Каждый токен классифицируется независимо (с контекстом ±1),
затем соседние токены одинаковой непустой роли склеиваются
в один span.

Стек: sklearn TfidfVectorizer(char_wb 2..4) + LogisticRegression.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .candidate_generator import tokenize
from .roles import Role


@dataclass
class TokenPrediction:
    token: str
    role: Role
    confidence: float
    start: int
    end: int


@dataclass
class SpanPrediction:
    role: Role
    value: str
    confidence: float
    span: tuple[int, int]


def _context_features(tokens: list[str], idx: int) -> str:
    left = tokens[idx - 1] if idx > 0 else "<s>"
    cur = tokens[idx]
    right = tokens[idx + 1] if idx + 1 < len(tokens) else "</s>"
    return f"{left} {cur} {right}"


class MLSlotTagger:
    def __init__(self, examples: list[dict], min_confidence: float = 0.30):
        self._examples = list(examples or [])
        self._min_confidence = float(min_confidence)
        self._pipeline = None
        self._classes: list[str] = []
        self._built = False

    def _build(self) -> None:
        if self._built:
            return
        self._built = True

        features: list[str] = []
        labels: list[str] = []
        for ex in self._examples:
            toks = [t for t, _ in ex["tokens"]]
            for i, (tok, role) in enumerate(ex["tokens"]):
                features.append(_context_features(toks, i))
                labels.append(role)

        if len(features) < 5 or len(set(labels)) < 2:
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
            ("clf", LogisticRegression(max_iter=500)),
        ])

        try:
            pipeline.fit(features, labels)
        except Exception:
            self._pipeline = None
            self._classes = []
            return

        self._pipeline = pipeline
        self._classes = list(pipeline.named_steps["clf"].classes_)

    def _predict_token(self, features: str) -> tuple[Role, float]:
        if self._pipeline is None:
            return Role.O, 0.0
        try:
            proba = self._pipeline.predict_proba([features])[0]
        except Exception:
            return Role.O, 0.0
        if len(proba) == 0:
            return Role.O, 0.0
        best_idx = int(max(range(len(proba)), key=lambda i: proba[i]))
        best_conf = float(proba[best_idx])
        try:
            role = Role(self._classes[best_idx])
        except ValueError:
            role = Role.O
        return role, best_conf

    def predict(self, text: str) -> list[SpanPrediction]:
        self._build()
        if self._pipeline is None:
            return []

        tokens_with_spans = tokenize(text)
        if not tokens_with_spans:
            return []

        tokens = [t for t, _, _ in tokens_with_spans]

        token_preds: list[TokenPrediction] = []
        for i, (tok, s, e) in enumerate(tokens_with_spans):
            feats = _context_features(tokens, i)
            role, conf = self._predict_token(feats)
            if conf < self._min_confidence or role == Role.O:
                role = Role.O
            token_preds.append(TokenPrediction(tok, role, conf, s, e))

        spans: list[SpanPrediction] = []
        cur_role: Optional[Role] = None
        cur_start: Optional[int] = None
        cur_end: Optional[int] = None
        cur_confs: list[float] = []

        def flush():
            nonlocal cur_role, cur_start, cur_end, cur_confs
            if cur_role is not None and cur_role != Role.O and cur_start is not None:
                spans.append(SpanPrediction(
                    role=cur_role,
                    value=text[cur_start:cur_end] if cur_end is not None else "",
                    confidence=sum(cur_confs) / len(cur_confs),
                    span=(cur_start, cur_end if cur_end is not None else cur_start),
                ))
            cur_role = None
            cur_start = None
            cur_end = None
            cur_confs = []

        for tp in token_preds:
            if tp.role == Role.O:
                flush()
                continue
            if cur_role is None:
                cur_role = tp.role
                cur_start = tp.start
                cur_end = tp.end
                cur_confs = [tp.confidence]
            elif tp.role == cur_role:
                cur_end = tp.end
                cur_confs.append(tp.confidence)
            else:
                flush()
                cur_role = tp.role
                cur_start = tp.start
                cur_end = tp.end
                cur_confs = [tp.confidence]

        flush()
        return spans
