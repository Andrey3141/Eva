"""
Fallback извлечения topic для open_video.

Принцип: найти маркер "видео"/"ролик" и взять остаток.
"""
from __future__ import annotations


_VIDEO_MARKERS = (
    "видео",
    "видеозапись",
    "видеозаписи",
    "ролик",
    "ролики",
    "ролика",
    "фильм",
    "фильмы",
)


def extract_topic(text: str) -> dict:
    """
    "открой видео руководство по эксплуатации Кассового аппарата Titan Plus"
        → {"topic": "руководство по эксплуатации Кассового аппарата Titan Plus"}

    "включи ролик про трансформаторы"
        → {"topic": "про трансформаторы"}

    "открой видео"
        → {}
    """
    if not text:
        return {}

    low = text.lower()

    best_pos = -1
    best_marker = ""
    for m in _VIDEO_MARKERS:
        p = low.find(m)
        if p < 0:
            continue
        if p > best_pos:
            best_pos = p
            best_marker = m

    if best_pos < 0:
        return {}

    tail = text[best_pos + len(best_marker):].strip()
    tail = tail.lstrip(",.!?;:—- ").strip()
    if not tail:
        return {}

    return {"topic": tail}
