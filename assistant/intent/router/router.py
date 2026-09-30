"""
IntentRouter — каскадный классификатор Intent для EVA.

Порядок:
  1. Локально уверенно (fusion >= threshold) → Intent, used_llm=False.
  2. LLM fallback.
  3. Structural override — если LLM не помогла.
  4. UNKNOWN.
"""
from __future__ import annotations

from typing import Optional

from ..base import Intent, IntentParser
from .embedding_router import EmbeddingRouter
from .fusion import IntentFusion
from .llm_router import LLMIntentRouter
from .ml_classifier import MLIntentClassifier
from .parameter_extractor import ParameterExtractor
from .types import RouterDecision


# ---------------------------------------------------------------------------
# Структурный override
# ---------------------------------------------------------------------------

_COMMANDS = ("открой", "включи", "покажи", "запусти", "воспроизведи")
_CLOSE_VERBS = ("закрой", "закрыть", "останови", "остановить")
_RESTART_VERBS = ("переоткрой", "переоткрыть", "обнови", "обновить",
                  "перезапусти", "перезапустить")

_VIDEO_MARKERS = ("видео", "ролик", "видеозапись")
_PRES_MARKERS = ("презентац", "слайд")
_EXCEL_MARKERS = ("excel", "журнал", "таблиц")


def _structural_override(text: str) -> Optional[str]:
    """
    Структурный override для очевидных команд.

    Применяется как fallback — после того, как локальный routing
    и LLM не дали уверенного результата.
    """
    low = (text or "").lower()
    if not low:
        return None

    is_open = any(c in low for c in _COMMANDS)
    is_close = any(c in low for c in _CLOSE_VERBS)
    is_restart = any(c in low for c in _RESTART_VERBS)

    has_video = any(m in low for m in _VIDEO_MARKERS)
    has_pres = any(m in low for m in _PRES_MARKERS)
    has_excel = any(m in low for m in _EXCEL_MARKERS)

    if is_restart:
        if has_pres:
            return "restart_presentation"
        if has_excel:
            return "restart_excel"
        return None

    if is_close:
        if has_pres:
            return "close_presentation"
        if has_video:
            return "close_video"
        if has_excel:
            return "close_excel"
        return "close_file"

    if is_open:
        if has_video:
            return "open_video"
        if has_pres:
            return "open_presentation"
        if has_excel:
            return "open_excel"

    return None


class IntentRouter(IntentParser):
    def __init__(
        self,
        embedding_router: EmbeddingRouter,
        ml_classifier: MLIntentClassifier,
        fusion: IntentFusion,
        llm_router: LLMIntentRouter,
        confidence_threshold: float = 0.75,
        parameter_extractor: ParameterExtractor | None = None,
        parameter_router=None,
    ):
        self._emb = embedding_router
        self._ml = ml_classifier
        self._fusion = fusion
        self._llm = llm_router
        self._threshold = float(confidence_threshold)

        self._extractor = parameter_extractor or ParameterExtractor()
        self._param_router = parameter_router

        self.last_decision: RouterDecision | None = None
        self.llm_calls: int = 0

    def _extract_params(self, text: str, intent_name: str) -> dict:
        if self._param_router is not None:
            try:
                params, _accepted, _rejected, _debug = \
                    self._param_router.extract_params(text, intent_name)
                return params
            except Exception as e:
                print(
                    f"[IntentRouter] parameter_router error: "
                    f"{type(e).__name__}: {e}",
                    flush=True,
                )
        return self._extractor.extract(text, intent_name)

    def route(self, text: str) -> RouterDecision:
        emb_pred = self._emb.predict(text)
        ml_pred = self._ml.predict(text)
        fused = self._fusion.fuse(emb_pred, ml_pred)

        print(
            f"[IntentRouter] text={text!r}\n"
            f"    emb={emb_pred.intent!r}/{emb_pred.confidence:.3f}\n"
            f"    ml={ml_pred.intent!r}/{ml_pred.confidence:.3f}\n"
            f"    fused={fused.intent!r}/{fused.confidence:.3f} "
            f"agree={fused.agree}\n"
            f"    threshold={self._threshold:.3f}",
            flush=True,
        )

        # 1. Локально уверенно.
        if fused.intent and fused.confidence >= self._threshold:
            params = self._extract_params(text, fused.intent)
            print(
                f"[IntentRouter] → local: intent={fused.intent!r} "
                f"params={params!r}",
                flush=True,
            )
            decision = RouterDecision(
                intent=Intent(
                    name=fused.intent, params=params,
                    confidence=fused.confidence, raw_text=text,
                ),
                source="fusion",
                confidence=fused.confidence,
                used_llm=False,
            )
            self.last_decision = decision
            return decision

        # 2. LLM fallback.
        llm_pred = self._llm.route(text)
        self.llm_calls += 1

        print(
            f"[IntentRouter] → LLM fallback: "
            f"llm={llm_pred.intent!r}/{llm_pred.confidence:.3f} "
            f"params={llm_pred.params!r}",
            flush=True,
        )

        if llm_pred.intent and llm_pred.confidence >= self._threshold:
            params = dict(llm_pred.params or {})
            if not params:
                params = self._extract_params(text, llm_pred.intent)

            print(
                f"[IntentRouter] → LLM accepted: intent={llm_pred.intent!r} "
                f"params={params!r}",
                flush=True,
            )
            decision = RouterDecision(
                intent=Intent(
                    name=llm_pred.intent, params=params,
                    confidence=llm_pred.confidence, raw_text=text,
                ),
                source="llm",
                confidence=llm_pred.confidence,
                used_llm=True,
            )
            self.last_decision = decision
            return decision

        # 3. Structural override — LLM не помогла.
        structural = _structural_override(text)
        if structural is not None:
            params = self._extract_params(text, structural)
            print(
                f"[IntentRouter] → structural override (after LLM): "
                f"intent={structural!r} params={params!r}",
                flush=True,
            )
            decision = RouterDecision(
                intent=Intent(
                    name=structural, params=params,
                    confidence=0.85, raw_text=text,
                ),
                source="structural",
                confidence=0.85,
                used_llm=True,
            )
            self.last_decision = decision
            return decision

        # 4. UNKNOWN.
        print(
            f"[IntentRouter] → unknown (llm conf={llm_pred.confidence:.3f} "
            f"< {self._threshold:.3f})",
            flush=True,
        )
        decision = RouterDecision(
            intent=Intent(
                name="unknown", params={},
                confidence=float(llm_pred.confidence or 0.0),
                raw_text=text,
            ),
            source="unknown",
            confidence=float(llm_pred.confidence or 0.0),
            used_llm=True,
        )
        self.last_decision = decision
        return decision

    def parse(self, user_command: str) -> list[Intent]:
        decision = self.route(user_command)
        return [decision.intent]
