"""
EmbeddingCandidateScorer — семантический источник кандидатов.

Отвечает только на вопрос "насколько фрагмент семантически похож
на значение роли X". Не выполняет typed-валидацию — это Fusion.

Возвращает top_k лучших по semantic score плюс extra_candidates
структурно-возможных кандидатов с низким score, чтобы Fusion мог
применить typed-валидатор (числовые значения grade и т.п.).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..router.providers import EmbeddingProvider, get_default_embedding_provider
from .candidate_generator import generate_span_candidates
from .roles import (
    Role, ROLE_SIGNATURES,
    is_topic_marker, is_command_word, is_object_word,
)


@dataclass
class EmbeddingCandidate:
    role: Role
    value: str
    confidence: float
    span: tuple[int, int]


class EmbeddingCandidateScorer:
    def __init__(
        self,
        provider: EmbeddingProvider | None = None,
        max_span_tokens: int = 5,
        top_k: int = 5,
        extra_candidates: int = 3,
        min_confidence: float = 0.0,
        debug: bool = False,
    ):
        self._provider = provider or get_default_embedding_provider()
        self._max_span_tokens = int(max_span_tokens)
        self._top_k = int(top_k)
        self._extra_candidates = int(extra_candidates)
        self._min_confidence = float(min_confidence)
        self._debug = bool(debug)
        self._sig_cache: dict[Role, np.ndarray | None] = {}

    # ------------------------------------------------------------------
    def _signature_matrix(self, role: Role) -> np.ndarray | None:
        if role in self._sig_cache:
            return self._sig_cache[role]
        texts = ROLE_SIGNATURES.get(role, [])
        if not texts:
            self._sig_cache[role] = None
            return None
        try:
            vecs = self._provider.embed(texts, role="passage")
        except Exception:
            self._sig_cache[role] = None
            return None
        m = np.asarray(vecs, dtype="float32")
        self._sig_cache[role] = m
        return m

    # ------------------------------------------------------------------
    def score_role(self, text: str, role: Role) -> list[EmbeddingCandidate]:
        sig_matrix = self._signature_matrix(role)
        if sig_matrix is None:
            return []

        raw_candidates = generate_span_candidates(
            text, max_len=self._max_span_tokens,
        )
        if not raw_candidates:
            return []

        filtered = [
            c for c in raw_candidates
            if self._is_structurally_valid(c.value, role)
        ]
        if not filtered:
            return []

        seen: set[str] = set()
        unique = []
        for c in filtered:
            key = c.value.strip().lower()
            if key in seen:
                continue
            seen.add(key)
            unique.append(c)

        values = [c.value for c in unique]
        try:
            vecs = self._provider.embed(values, role="query")
        except Exception:
            return []

        all_scored: list[EmbeddingCandidate] = []
        for c, v in zip(unique, vecs):
            varr = np.asarray(v, dtype="float32")
            sims = sig_matrix @ varr
            best = float(np.max(sims)) if sims.size else 0.0
            if best < self._min_confidence:
                continue
            all_scored.append(EmbeddingCandidate(
                role=role, value=c.value,
                confidence=best, span=c.span,
            ))

        if not all_scored:
            return []

        all_scored.sort(
            key=lambda x: (x.confidence, x.span[1] - x.span[0]),
            reverse=True,
        )

        top = all_scored[:self._top_k]
        if self._extra_candidates > 0:
            top = top + all_scored[self._top_k:self._top_k + self._extra_candidates]

        if self._debug:
            for c in top:
                print(
                    f"[PARAM_EMB] role={role.value.lower()} "
                    f"candidate={c.value!r} score={c.confidence:.3f}",
                    flush=True,
                )
        return top

    # ------------------------------------------------------------------
    @staticmethod
    def _is_structurally_valid(value: str, role: Role) -> bool:
        """
        Только структурная проверка. Не выполняет typed validation.
        """
        s = (value or "").strip()
        if not s:
            return False
        low = s.lower()
        tokens = low.split()
        if not tokens:
            return False

        if len(low) <= 2:
            if not low.isdigit():
                return False

        if role == Role.TOPIC:
            # Число не является структурным кандидатом темы.
            if len(tokens) == 1 and tokens[0].isdigit():
                return False
            if len(tokens) == 1 and is_topic_marker(tokens[0]):
                return False
            if all(is_topic_marker(t) or is_command_word(t) or is_object_word(t)
                   for t in tokens):
                return False
            if is_topic_marker(tokens[0]):
                return False
            if is_command_word(tokens[0]):
                return False
            if len(tokens) == 1 and is_object_word(tokens[0]):
                return False
            if not any(
                (not is_topic_marker(t))
                and (not is_command_word(t))
                and (not is_object_word(t))
                for t in tokens
            ):
                return False
            return True

        if role == Role.STUDENT:
            if len(tokens) > 4:
                return False
            if all(is_command_word(t) or is_object_word(t) or is_topic_marker(t)
                   for t in tokens):
                return False
            if any(is_command_word(t) or is_object_word(t) for t in tokens):
                return False
            if len(tokens) == 1 and tokens[0].isdigit():
                return False
            return True

        if role == Role.GRADE:
            if any(is_command_word(t) for t in tokens):
                return False
            if any(is_object_word(t) for t in tokens):
                return False
            if any(is_topic_marker(t) for t in tokens):
                return False
            return True

        if role == Role.COMMAND:
            return any(is_command_word(t) for t in tokens)

        if role == Role.OBJECT:
            return any(is_object_word(t) for t in tokens)

        return True
