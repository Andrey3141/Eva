"""Типы для ParameterRouter."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ParameterPrediction:
    """
    Одно предсказание параметра.

    name  — имя параметра ("topic", "student", "grade", ...)
    value — нормализованное значение ("итоговые занятия", "8")
    span  — (start, end) в исходном тексте, если известно
    confidence — [0, 1]
    source — "ml" | "embedding" | "fusion"
    """
    name: str = ""
    value: str = ""
    confidence: float = 0.0
    source: str = ""
    span: tuple[int, int] | None = None


@dataclass
class ParameterFusionResult:
    """
    Результат fusion: какие параметры приняты и с какой уверенностью.

    accepted — список ParameterPrediction с source="fusion"
    rejected — те, что не прошли порог (для отладки)
    """
    accepted: list[ParameterPrediction] = field(default_factory=list)
    rejected: list[ParameterPrediction] = field(default_factory=list)
