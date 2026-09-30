"""
Локальное извлечение параметров Intent.

Не меняет intent — только заполняет params. Классификация и extraction
разделены: IntentRouter решает "что", ParameterExtractor — "с какими
параметрами".

Правила по intent:
  grade_student:
      "поставь Иванову четыре"  → {"student": "Иванову", "grade": 4}
      "Сидоров 2"               → {"student": "Сидоров", "grade": 2}
      "сколько будет 2 плюс 2"  → {} (не grade_student extraction)

  open_video / open_presentation:
      "включи видео про электричество"      → {"topic": "электричество"}
      "открой презентацию по физике"        → {"topic": "физике"}
      "покажи слайды по электробезопасности" → {"topic": "электробезопасности"}
      "включи видео"                        → {} (не выдумывать)

  next_slide / answer:
      → {}

Если extraction не удался — возвращается пустой dict.
"""
from __future__ import annotations

import re


# ---------------------------------------------------------------------------
# grade_student
# ---------------------------------------------------------------------------

_GRADE_WORDS = {
    "два": 2, "двойка": 2, "двойку": 2, "двойке": 2,
    "три": 3, "тройка": 3, "тройку": 3, "тройке": 3,
    "четыре": 4, "четвёрка": 4, "четверка": 4,
    "четвёрку": 4, "четверку": 4,
    "пять": 5, "пятёрка": 5, "пятерка": 5,
    "пятёрку": 5, "пятерку": 5,
}

_GRADE_WORD_ALT = "|".join(re.escape(w) for w in _GRADE_WORDS)

_GRADE_VERBS = r"(?:постав[ьи]|выстав[ьи]|дай|вкати|вл[ея]пи|запиши|простав[ьи])"

_NAME = r"[А-ЯЁA-Z][а-яёa-z\-]{1,}"

_GRADE_RE = re.compile(
    rf"(?:{_GRADE_VERBS}\s+)?"
    rf"(?P<student>{_NAME})\s+"
    rf"(?:оценку\s+|балл(?:ов|а)?\s+)?"
    rf"(?:(?P<grade_digit>[2-5])\b|(?P<grade_word>{_GRADE_WORD_ALT})\b)",
    re.IGNORECASE,
)

_MATH_MARKERS = re.compile(
    r"(?:сколько\s+будет|вычисли|посчитай|плюс|минус|умножить|разделить|"
    r"сложи|вычти|раздели|итого|сумма)",
    re.IGNORECASE,
)


def _extract_grade_student(text: str) -> dict:
    if not text:
        return {}

    if _MATH_MARKERS.search(text):
        if not re.search(_GRADE_VERBS, text, re.IGNORECASE):
            return {}

    m = _GRADE_RE.search(text)
    if not m:
        return {}

    student = (m.group("student") or "").strip()
    if not student:
        return {}

    grade: int | None = None
    digit = m.group("grade_digit")
    if digit:
        try:
            v = int(digit)
            if v in (2, 3, 4, 5):
                grade = v
        except ValueError:
            grade = None
    else:
        word = (m.group("grade_word") or "").lower()
        grade = _GRADE_WORDS.get(word)

    if grade is None:
        return {}

    return {"student": student, "grade": grade}


# ---------------------------------------------------------------------------
# open_video / open_presentation: тема
# ---------------------------------------------------------------------------

# \b перед группой гарантирует, что маркер начинается с границы слова.
# Это критично для одиночного "о ": без \b оно матчится внутри слов
# вроде "видео " и даёт topic="про электричество".
#
# Порядок альтернатив важен: "об" ДО "о", иначе "об" съестся.
_TOPIC_MARKERS = re.compile(
    r"\b(?:"
    r"на\s+тему\s+"
    r"|про\s+"
    r"|об\s+"
    r"|о\s+"
    r"|по\s+"
    r")"
    r"(?P<topic>.+?)"
    r"(?:[.!?,;]|$)",
    re.IGNORECASE,
)

_GENERIC_TOPIC_WORDS = {
    "видео", "ролик", "видеозапись", "презентацию", "презентация",
    "слайды", "слайд", "фильм", "запись",
}


def _extract_topic(text: str) -> dict:
    if not text:
        return {}

    m = _TOPIC_MARKERS.search(text)
    if not m:
        return {}

    raw = (m.group("topic") or "").strip()
    raw = re.sub(r"[\s.,!?;:]+$", "", raw).strip()
    if not raw:
        return {}

    low = raw.lower()
    if low in _GENERIC_TOPIC_WORDS:
        return {}

    return {"topic": raw}


# ---------------------------------------------------------------------------
# ParameterExtractor
# ---------------------------------------------------------------------------

class ParameterExtractor:
    """
    Локальный action-specific extraction.

    Не меняет intent. Возвращает dict параметров, возможно пустой.
    Контракт параметров согласован с существующими Actions/Validators:

      grade_student       → {"student": str, "grade": int}
      open_video          → {"topic": str}
      open_presentation   → {"topic": str}
      next_slide, answer  → {}
    """

    def extract(self, text: str, intent: str) -> dict:
        if not text or not intent:
            return {}

        if intent == "grade_student":
            return _extract_grade_student(text)

        if intent in ("open_video", "open_presentation"):
            return _extract_topic(text)

        return {}
