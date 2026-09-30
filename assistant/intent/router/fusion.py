"""
Fusion локальных предсказаний (embedding + ML).

Правила (прозрачные, без скрытой математики):

  1. Оба дали один и тот же конкретный intent:
       confidence = max(emb, ml) + agree_bonus, ограничено max_confidence.
       FusionResult(intent=X, agree=True).

  2. Один дал конкретный intent, второй — пустой:
       берём конкретный, если его confidence >= min_individual.
       Иначе — не уверены.

  3. Оба дали РАЗНЫЕ конкретные intent:
       Fusion НЕ выбирает победителя. intent=None. → LLM fallback.
       Даже если один сильно увереннее другого.

  4. Оба пустые / оба ниже min_individual:
       intent=None. → LLM fallback.

Смысл: локальный каскад не должен «угадывать» при конфликте —
решение уходит в LLM Router.
"""
from __future__ import annotations

from .types import FusionResult, IntentPrediction


class IntentFusion:
    def __init__(
        self,
        min_individual: float = 0.55,
        agree_bonus: float = 0.05,
        max_confidence: float = 1.0,
    ):
        self.min_individual = float(min_individual)
        self.agree_bonus = float(agree_bonus)
        self.max_confidence = float(max_confidence)

    def fuse(
        self,
        emb: IntentPrediction,
        ml: IntentPrediction,
    ) -> FusionResult:
        emb_intent = emb.intent or ""
        ml_intent = ml.intent or ""
        emb_conf = float(emb.confidence)
        ml_conf = float(ml.confidence)

        detail = {
            "embedding_intent": emb_intent or None,
            "embedding_confidence": emb_conf,
            "ml_intent": ml_intent or None,
            "ml_confidence": ml_conf,
        }

        # --- Случай 3: конфликт двух конкретных intent ---
        if emb_intent and ml_intent and emb_intent != ml_intent:
            return FusionResult(
                intent=None,
                confidence=max(emb_conf, ml_conf),
                agree=False,
                detail=detail,
            )

        # --- Случай 1: согласие ---
        if emb_intent and ml_intent and emb_intent == ml_intent:
            conf = min(
                max(emb_conf, ml_conf) + self.agree_bonus,
                self.max_confidence,
            )
            return FusionResult(
                intent=emb_intent,
                confidence=conf,
                agree=True,
                detail=detail,
            )

        # --- Случай 2: один конкретный, второй пустой ---
        if emb_intent and not ml_intent:
            if emb_conf >= self.min_individual:
                return FusionResult(
                    intent=emb_intent,
                    confidence=emb_conf,
                    agree=False,
                    detail=detail,
                )
            return FusionResult(
                intent=None,
                confidence=emb_conf,
                agree=False,
                detail=detail,
            )

        if ml_intent and not emb_intent:
            if ml_conf >= self.min_individual:
                return FusionResult(
                    intent=ml_intent,
                    confidence=ml_conf,
                    agree=False,
                    detail=detail,
                )
            return FusionResult(
                intent=None,
                confidence=ml_conf,
                agree=False,
                detail=detail,
            )

        # --- Случай 4: оба пустые ---
        return FusionResult(
            intent=None,
            confidence=max(emb_conf, ml_conf),
            agree=False,
            detail=detail,
        )
