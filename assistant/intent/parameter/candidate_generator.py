"""
Генератор кандидатов-фрагментов из текста.

Возвращает все contiguous span'ы длины 1..max_len токенов
с указанием границ. Используется и ML-slot-tagger'ом (для
обучения/постобработки), и embedding-скорером (для
независимого скоринга).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SpanCandidate:
    value: str
    span: tuple[int, int]
    n_tokens: int


def _tokenize_with_spans(text: str) -> list[tuple[str, int, int]]:
    """Токенизация по пробелам с сохранением span."""
    out: list[tuple[str, int, int]] = []
    i = 0
    n = len(text)
    while i < n:
        while i < n and text[i].isspace():
            i += 1
        if i >= n:
            break
        start = i
        while i < n and not text[i].isspace():
            i += 1
        out.append((text[start:i], start, i))
    return out


def generate_span_candidates(
    text: str,
    max_len: int = 5,
) -> list[SpanCandidate]:
    """
    Все contiguous span'ы длины 1..max_len токенов.

    Например для "открой презентацию итоговые занятия":
      "открой", "презентацию", "итоговые", "занятия",
      "открой презентацию", "презентацию итоговые",
      "итоговые занятия", "открой презентацию итоговые",
      "презентацию итоговые занятия",
      "открой презентацию итоговые занятия"
    """
    tokens = _tokenize_with_spans(text)
    out: list[SpanCandidate] = []
    n = len(tokens)
    for i in range(n):
        for length in range(1, max_len + 1):
            j = i + length
            if j > n:
                break
            start = tokens[i][1]
            end = tokens[j - 1][2]
            value = text[start:end]
            out.append(SpanCandidate(
                value=value,
                span=(start, end),
                n_tokens=length,
            ))
    return out


def tokenize(text: str) -> list[tuple[str, int, int]]:
    return _tokenize_with_spans(text)
