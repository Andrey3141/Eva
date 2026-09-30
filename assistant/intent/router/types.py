"""Типы данных для каскадного Intent Router."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class IntentPrediction:
    """Предсказание одного классификатора (embedding/ML/LLM)."""
    intent: str = ""
    confidence: float = 0.0
    source: str = ""              # "embedding" | "ml" | "llm"
    params: dict = field(default_factory=dict)


@dataclass
class FusionResult:
    """
    Результат fusion локальных предсказаний.

    intent=None означает «локально определить не удалось» →
    Router уходит в LLM fallback.
    """
    intent: Optional[str] = None
    confidence: float = 0.0
    agree: bool = False           # совпали ли источники
    detail: dict = field(default_factory=dict)


@dataclass
class RouterDecision:
    """
    Итоговое решение IntentRouter.

    intent  — финальный Intent (может быть "unknown")
    source  — какой слой принял решение
    used_llm — был ли вызван LLM fallback (для метрик/тестов)
    """
    intent: object                # assistant.intent.base.Intent
    source: str                   # "fusion" | "llm" | "unknown"
    confidence: float = 0.0
    used_llm: bool = False
