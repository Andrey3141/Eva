"""
Fallback извлечения topic для open_presentation.

Принцип: найти маркер "презентация"/"презентацию" и взять остаток.

Никаких ML/embedding. Просто и прозрачно.
"""
from __future__ import annotations


_PRESENTATION_MARKERS = (
    "презентацию",
    "презентации",
    "презентация",
    "презентацией",
    "слайды",
    "слайд",
    "слайдов",
)


def extract_topic(text: str) -> dict:
    """
    "открой презентацию итоговое занятие" → {"topic": "итоговое занятие"}
    "открой презентацию по охране труда"  → {"topic": "по охране труда"}
    "открой презентацию"                  → {}
    """
    if not text:
        return {}

    low = text.lower()

    # Ищем самый поздний по позиции маркер, чтобы не поймать служебное
    # слово раньше основного. Для "открой презентацию" это "презентацию".
    best_pos = -1
    best_marker = ""
    for m in _PRESENTATION_MARKERS:
        p = low.find(m)
        if p < 0:
            continue
        if p > best_pos:
            best_pos = p
            best_marker = m

    if best_pos < 0:
        return {}

    tail = text[best_pos + len(best_marker):].strip()
    # Убираем ведущую пунктуацию.
    tail = tail.lstrip(",.!?;:—- ").strip()
    if not tail:
        return {}

    return {"topic": tail}
