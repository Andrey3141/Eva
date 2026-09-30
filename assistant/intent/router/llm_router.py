"""
LLM fallback для определения Intent.

Обёртка над существующим LLMIntentParser: получает текст, возвращает
IntentPrediction по первому интенту. Компактный system-prompt уже
задан в LLMIntentParser (см. assistant/intent/llm_intent_parser.py).

LLM НЕ вызывается, если локальный fusion уверен.
"""
from __future__ import annotations

from typing import Optional

from ..llm_intent_parser import LLMIntentParser
from .types import IntentPrediction


class LLMIntentRouter:
    def __init__(self, llm):
        self._llm = llm
        self._parser = LLMIntentParser(llm)

    def route(self, text: str) -> IntentPrediction:
        if not text or not text.strip():
            return IntentPrediction(intent="", confidence=0.0, source="llm")

        try:
            intents = self._parser.parse(text)
        except Exception as e:
            return IntentPrediction(
                intent="",
                confidence=0.0,
                source="llm",
                params={"error": f"{type(e).__name__}: {e}"},
            )

        if not intents:
            return IntentPrediction(intent="", confidence=0.0, source="llm")

        first = intents[0]
        return IntentPrediction(
            intent=first.name or "",
            confidence=float(first.confidence or 0.0),
            source="llm",
            params=dict(first.params or {}),
        )
