"""
ParameterRouter — каскадное извлечение параметров Intent.

text + intent
    ├── MLSlotTagger             → ML span-кандидаты по ролям
    │
    └── EmbeddingCandidateScorer → независимые top-K кандидаты по ролям
                                   ↓
                            ParameterFusion
                                   ↓
                       accepted params (сырые)
                                   ↓
                    _resolve_cross_param_conflicts
                                   ↓
                       final params (финальные)
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..base import Intent
from .embedding_candidate_scorer import EmbeddingCandidateScorer
from .fusion import ParameterFusion, MLCandidate, EmbCandidate
from .ml_slot_tagger import MLSlotTagger, SpanPrediction
from .roles import (
    Role, INTENT_PARAM_SCHEMA, coerce_grade, passes_type,
    is_command_word, is_object_word, is_topic_marker,
)
from .types import ParameterPrediction


# Токены-связки, которые не должны становиться ни темой, ни учеником.
_GLUE_TOKENS = {
    "и", "а", "но", "или", "также", "ещё", "еще", "же",
    "на", "в", "во", "с", "со", "к", "ко", "по", "о", "об", "обо",
    "про", "для", "от", "до", "из", "за",
}


@dataclass
class ParameterRouterResult:
    params: dict = field(default_factory=dict)
    accepted: list[ParameterPrediction] = field(default_factory=list)
    rejected: list[ParameterPrediction] = field(default_factory=list)
    debug: dict = field(default_factory=dict)


class ParameterRouter:
    def __init__(
        self,
        ml_tagger: MLSlotTagger,
        embedding_scorer: EmbeddingCandidateScorer,
        fusion: ParameterFusion,
    ):
        self._ml = ml_tagger
        self._emb = embedding_scorer
        self._fusion = fusion

    def extract(self, text: str, intent: Intent) -> ParameterRouterResult:
        params, accepted, rejected, debug = self.extract_params(text, intent.name)
        return ParameterRouterResult(
            params=params, accepted=accepted,
            rejected=rejected, debug=debug,
        )

    def extract_params(
        self,
        text: str,
        intent_name: str,
    ) -> tuple[dict, list[ParameterPrediction], list[ParameterPrediction], dict]:
        schema = INTENT_PARAM_SCHEMA.get(intent_name)
        if not schema:
            return {}, [], [], {}

        ml_spans = self._ml.predict(text)
        accepted: list[ParameterPrediction] = []
        rejected: list[ParameterPrediction] = []
        debug: dict = {"ml_spans": [], "emb_candidates": {}, "fusion": {}}

        for sp in ml_spans:
            debug["ml_spans"].append({
                "role": sp.role.value,
                "value": sp.value,
                "span": list(sp.span),
                "confidence": round(sp.confidence, 3),
            })

        for param_name, role in schema.items():
            ml_for_role = [s for s in ml_spans if s.role == role]
            ml_candidates = [
                MLCandidate(role=s.role, value=s.value,
                            confidence=s.confidence, span=s.span)
                for s in ml_for_role
            ]

            emb_scores = self._emb.score_role(text, role)
            emb_candidates = [
                EmbCandidate(role=e.role, value=e.value,
                             confidence=e.confidence, span=e.span)
                for e in emb_scores
            ]

            debug["emb_candidates"][param_name] = [
                {"value": e.value, "span": list(e.span),
                 "confidence": round(e.confidence, 3)}
                for e in emb_candidates
            ]

            fusion_res = self._fusion.fuse(
                param_name=param_name,
                role=role,
                ml_candidates=ml_candidates,
                emb_candidates=emb_candidates,
            )
            accepted.extend(fusion_res.accepted)
            rejected.extend(fusion_res.rejected)

            debug["fusion"][param_name] = {
                "accepted": [
                    {"value": p.value, "confidence": round(p.confidence, 3),
                     "source": p.source}
                    for p in fusion_res.accepted
                ],
                "rejected": [
                    {"value": p.value, "confidence": round(p.confidence, 3),
                     "source": p.source}
                    for p in fusion_res.rejected
                ],
            }

        # --- Финальное разрешение конфликтов между параметрами ---
        accepted = self._resolve_cross_param_conflicts(
            accepted=accepted,
            ml_spans=ml_spans,
            text=text,
        )

        # params: одно значение на имя.
        params: dict = {}
        for p in accepted:
            if p.name not in params:
                params[p.name] = p.value

        if "grade" in params:
            g = coerce_grade(params["grade"])
            if g is not None:
                params["grade"] = g
            else:
                params.pop("grade", None)

        return params, accepted, rejected, debug

    # ------------------------------------------------------------------
    def _resolve_cross_param_conflicts(
        self,
        accepted: list[ParameterPrediction],
        ml_spans: list[SpanPrediction],
        text: str,
    ) -> list[ParameterPrediction]:
        """
        Разрешает конфликты между принятыми параметрами:

          1. Значение параметра обрезается по границам, чтобы не
             включать в себя другие принятые значения (например,
             student не должен содержать число grade).
          2. Ведущие/хвостовые служебные токены ("и", "а", "на", "по" ...)
             обрезаются, если они не входят в ML-якорь для этого параметра.
          3. Если у параметра есть ML-span, его границы используются
             как якорь: embedding-значение обрезается до пересечения
             с ML-span при сохранении содержательной части.
        """
        if not accepted:
            return accepted

        # Соберём ML-спаны по ролям.
        ml_by_role: dict[Role, list[SpanPrediction]] = {}
        for s in ml_spans:
            ml_by_role.setdefault(s.role, []).append(s)

        # Индекс: значения других параметров со своими span.
        spans_taken: list[tuple[int, int]] = []
        for p in accepted:
            if p.span and p.name != "grade":
                # grade-числа имеют очень короткий span, их не кладём
                # в "занятые" — наоборот, другие параметры должны
                # от них отрезаться.
                pass
        # Собираем span'ы GRADE-значений отдельно.
        grade_spans: list[tuple[int, int]] = [
            p.span for p in accepted if p.name == "grade" and p.span
        ]

        result: list[ParameterPrediction] = []

        for p in accepted:
            new_value = p.value
            new_span = p.span

            # --- (1) Обрезаем по GRADE-спанам ---
            if p.name != "grade" and p.span is not None and grade_spans:
                new_span, new_value = self._cut_out_spans(
                    text, p.span, grade_spans, p.value,
                )
                new_value = self._strip_glue(new_value)

            # --- (2) Обрезаем служебные токены на границах ---
            new_value = self._strip_glue(new_value)

            # --- (3) Если значение пустое после обрезки — не принимаем ---
            if not new_value:
                continue

            # --- (4) Применяем ML-якорь, если есть ---
            if p.span is not None:
                new_value, new_span = self._apply_ml_anchor(
                    p=p,
                    new_value=new_value,
                    new_span=new_span,
                    ml_by_role=ml_by_role,
                    text=text,
                )

            if not new_value:
                continue

            result.append(ParameterPrediction(
                name=p.name,
                value=new_value,
                confidence=p.confidence,
                source=p.source,
                span=new_span,
            ))

        return result

    # ------------------------------------------------------------------
    @staticmethod
    def _cut_out_spans(
        text: str,
        outer_span: tuple[int, int],
        cut_spans: list[tuple[int, int]],
        current_value: str,
    ) -> tuple[tuple[int, int], str]:
        """
        Убирает из значения пересечения с cut_spans.
        Работает по границам: если cut_span целиком внутри outer_span,
        обрезаем outer_span по левую или правую сторону от cut.
        """
        s, e = outer_span
        # Сортируем вырезы по позиции.
        cuts = sorted((cs, ce) for cs, ce in cut_spans
                      if not (ce <= s or cs >= e))
        if not cuts:
            return outer_span, current_value

        # Берём все внутренние пересечения и обрезаем внешний span:
        # оставляем часть до первого cut'а или после последнего.
        # Простейший безопасный вариант: обрезать внешний span
        # до участка, который не пересекается ни с одним cut.
        # Если между cuts остаются куски — берём самый длинный.
        fragments: list[tuple[int, int]] = []
        cursor = s
        for cs, ce in cuts:
            if cs > cursor:
                fragments.append((cursor, cs))
            cursor = max(cursor, ce)
        if cursor < e:
            fragments.append((cursor, e))

        if not fragments:
            return (s, s), ""  # всё вырезано

        # Берём самый длинный фрагмент.
        best = max(fragments, key=lambda f: f[1] - f[0])
        return best, text[best[0]:best[1]].strip()

    # ------------------------------------------------------------------
    @staticmethod
    def _strip_glue(value: str) -> str:
        """
        Убирает ведущие/хвостовые служебные токены ("и", "на", "по" ...).
        """
        tokens = (value or "").split()
        while tokens and tokens[0].lower().strip(",.!?;:") in _GLUE_TOKENS:
            tokens.pop(0)
        while tokens and tokens[-1].lower().strip(",.!?;:") in _GLUE_TOKENS:
            tokens.pop()
        return " ".join(tokens).strip()

    # ------------------------------------------------------------------
    @staticmethod
    def _apply_ml_anchor(
        p: ParameterPrediction,
        new_value: str,
        new_span: tuple[int, int] | None,
        ml_by_role: dict[Role, list[SpanPrediction]],
        text: str,
    ) -> tuple[str, tuple[int, int] | None]:
        """
        Если у параметра есть ML-span и он уже содержится в new_value —
        используем ML-span как якорь, чтобы не тащить лишние слова
        (например, "балла" в student).

        Логика: если ML-span для роли существует, и его span
        лежит внутри new_span, и ML-span непустой — предпочесть
        значение ML-спана. Это безопасно, потому что ML уже
        дал структурный якорь на уровне токенов.
        """
        role_map = {
            "student": Role.STUDENT,
            "grade": Role.GRADE,
            "topic": Role.TOPIC,
        }
        role = role_map.get(p.name)
        if role is None or new_span is None:
            return new_value, new_span

        candidates = ml_by_role.get(role, [])
        if not candidates:
            return new_value, new_span

        # Ищем ML-span, целиком лежащий внутри new_span.
        inside = [
            s for s in candidates
            if new_span[0] <= s.span[0] and s.span[1] <= new_span[1]
        ]
        if not inside:
            return new_value, new_span

        # Берём самый длинный ML-span, содержащийся в new_span.
        best = max(inside, key=lambda s: s.span[1] - s.span[0])
        ml_text = text[best.span[0]:best.span[1]].strip()
        if not ml_text:
            return new_value, new_span

        return ml_text, best.span
