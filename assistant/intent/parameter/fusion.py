"""
ParameterFusion — согласие ML и Embedding кандидатов с учётом
typed-валидации значения.

Правила:
  Для каждого параметра:
    1. Отбираем кандидатов, проходящих passes_type(param_name, value).
       Невалидные по типу — в rejected, не участвуют.
    2. Если валидных нет — параметр не принят.
    3. Среди валидных:
       - ML-лучший и Embedding-лучший;
       - если оба есть и согласны → fusion-accepted с бонусом;
       - если оба есть и конфликтуют → rejected (не угадываем);
       - если только один источник → принимаем его независимо
         от его score, если кандидат единственный typed-valid;
       - если оба есть, но один валиден, другой — нет → берём валидного.

Ключевое отличие от "max score":
    typed-валидность важнее semantic score. "8" с semantic=0.0
    может победить "оценку" с semantic=1.0, потому что первое
    валидно по типу, а второе — нет.
"""
from __future__ import annotations

from dataclasses import dataclass

from .roles import Role, passes_type
from .types import ParameterPrediction, ParameterFusionResult


@dataclass
class MLCandidate:
    role: Role
    value: str
    confidence: float
    span: tuple[int, int]


@dataclass
class EmbCandidate:
    role: Role
    value: str
    confidence: float
    span: tuple[int, int]


def _values_agree(a: str, b: str) -> bool:
    a = (a or "").strip().lower()
    b = (b or "").strip().lower()
    if not a or not b:
        return False
    if a == b:
        return True
    return a in b or b in a


class ParameterFusion:
    def __init__(
        self,
        min_ml: float = 0.40,
        min_emb: float = 0.45,
        agree_bonus: float = 0.10,
        max_confidence: float = 1.0,
    ):
        self.min_ml = float(min_ml)
        self.min_emb = float(min_emb)
        self.agree_bonus = float(agree_bonus)
        self.max_confidence = float(max_confidence)

    # ------------------------------------------------------------------
    def fuse(
        self,
        param_name: str,
        role: Role,
        ml_candidates: list[MLCandidate],
        emb_candidates: list[EmbCandidate],
    ) -> ParameterFusionResult:
        result = ParameterFusionResult()

        # 1. Разделяем на typed-valid и typed-invalid.
        ml_valid = [c for c in ml_candidates if passes_type(param_name, c.value)]
        ml_invalid = [c for c in ml_candidates if c not in ml_valid]

        emb_valid = [c for c in emb_candidates if passes_type(param_name, c.value)]
        emb_invalid = [c for c in emb_candidates if c not in emb_valid]

        # Невалидные по типу — в rejected для отладки.
        for c in ml_invalid:
            result.rejected.append(ParameterPrediction(
                name=param_name, value=c.value,
                confidence=c.confidence, source="ml",
                span=c.span,
            ))
        for c in emb_invalid:
            result.rejected.append(ParameterPrediction(
                name=param_name, value=c.value,
                confidence=c.confidence, source="embedding",
                span=c.span,
            ))

        ml_best = max(ml_valid, key=lambda c: c.confidence) if ml_valid else None
        emb_best = max(emb_valid, key=lambda c: c.confidence) if emb_valid else None

        # 2. Ничего typed-валидного нет.
        if ml_best is None and emb_best is None:
            return result

        # 3. Только ML typed-valid.
        if ml_best is not None and emb_best is None:
            if ml_best.confidence >= self.min_ml or len(ml_valid) == 1:
                result.accepted.append(ParameterPrediction(
                    name=param_name, value=ml_best.value,
                    confidence=ml_best.confidence,
                    source="ml", span=ml_best.span,
                ))
            else:
                result.rejected.append(ParameterPrediction(
                    name=param_name, value=ml_best.value,
                    confidence=ml_best.confidence,
                    source="ml", span=ml_best.span,
                ))
            return result

        # 4. Только Embedding typed-valid.
        if emb_best is not None and ml_best is None:
            if emb_best.confidence >= self.min_emb or len(emb_valid) == 1:
                result.accepted.append(ParameterPrediction(
                    name=param_name, value=emb_best.value,
                    confidence=emb_best.confidence,
                    source="embedding", span=emb_best.span,
                ))
            else:
                result.rejected.append(ParameterPrediction(
                    name=param_name, value=emb_best.value,
                    confidence=emb_best.confidence,
                    source="embedding", span=emb_best.span,
                ))
            return result

        # 5. Оба источника имеют typed-valid кандидата.
        assert ml_best is not None and emb_best is not None

        if _values_agree(ml_best.value, emb_best.value):
            chosen = (ml_best if len(ml_best.value) >= len(emb_best.value)
                      else emb_best)
            conf = min(
                max(ml_best.confidence, emb_best.confidence) + self.agree_bonus,
                self.max_confidence,
            )
            result.accepted.append(ParameterPrediction(
                name=param_name, value=chosen.value,
                confidence=conf,
                source="fusion", span=chosen.span,
            ))
            return result

        # Расхождение ML vs Embedding, оба typed-valid, значения разные.
        if len(ml_valid) == 1 and len(emb_valid) == 1:
            # Оба дали ровно одного валидного кандидата, но разных.
            # Не угадываем — оба в rejected.
            result.rejected.append(ParameterPrediction(
                name=param_name, value=ml_best.value,
                confidence=ml_best.confidence,
                source="ml", span=ml_best.span,
            ))
            result.rejected.append(ParameterPrediction(
                name=param_name, value=emb_best.value,
                confidence=emb_best.confidence,
                source="embedding", span=emb_best.span,
            ))
            return result

        # Иначе — берём того, кто лучше по confidence.
        if ml_best.confidence >= emb_best.confidence:
            result.accepted.append(ParameterPrediction(
                name=param_name, value=ml_best.value,
                confidence=ml_best.confidence,
                source="ml", span=ml_best.span,
            ))
        else:
            result.accepted.append(ParameterPrediction(
                name=param_name, value=emb_best.value,
                confidence=emb_best.confidence,
                source="embedding", span=emb_best.span,
            ))
        return result
