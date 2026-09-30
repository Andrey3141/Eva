"""
Fallback извлечения student + grade для grade_student.

Два шаблона:

A. С командой "поставь/выставь/дай":
     поставь Иванову два
     поставь Иванову два балла
     поставь Иванову 2
   → student = Иванову, grade = 2

B. Без команды:
     Иванову 2
   → первый значимый фрагмент = student, второй = grade.

Числительные и цифры приводятся к int.

"балл", "балла", "баллов", "оценку", "оценка" игнорируются.
"""
from __future__ import annotations

import re


_GRADE_WORDS = {
    "один": 1, "одна": 1, "единица": 1,
    "два": 2, "две": 2, "двойка": 2,
    "три": 3, "тройка": 3,
    "четыре": 4, "четвёрка": 4, "четверка": 4,
    "пять": 5, "пятёрка": 5, "пятерка": 5,
    "шесть": 6, "шестёрка": 6, "шестерка": 6,
    "семь": 7, "семёрка": 7, "семерка": 7,
    "восемь": 8, "восьмёрка": 8, "восьмерка": 8,
    "девять": 9, "девятка": 9,
    "десять": 10, "десятка": 10,
}

# Служебные слова, которые игнорируем.
_SERVICE_WORDS = {
    "поставь", "поставьте", "выставь", "выставьте", "дай", "дайте",
    "оценку", "оценка", "оценки", "балл", "балла", "баллов", "баллы",
    "ему", "ей", "за", "по", "в", "на",
}

_NAME_RE = re.compile(r"^[А-ЯЁA-Z][а-яёa-z\-]+$")


def _coerce_grade(token: str) -> int | None:
    low = (token or "").strip().lower().rstrip(",.!?;:")
    if not low:
        return None
    if low.isdigit():
        try:
            v = int(low)
        except ValueError:
            return None
        if 1 <= v <= 10:
            return v
        return None
    return _GRADE_WORDS.get(low)


def extract_params(text: str) -> dict:
    """
    Возвращает {"student": ..., "grade": ...} или пустой dict.
    """
    if not text:
        return {}

    tokens = [t for t in text.strip().split() if t]
    if not tokens:
        return {}

    # Убираем служебные слова, но сохраняем их позиции.
    filtered: list[str] = []
    for t in tokens:
        low = t.lower().rstrip(",.!?;:")
        if low in _SERVICE_WORDS:
            continue
        filtered.append(t)

    if len(filtered) < 2:
        return {}

    # Ищем первый токен, который может быть фамилией, и первый, который
    # может быть оценкой. Обычно порядок: [student, grade] или
    # [grade] отдельно (тогда student не находим).
    student: str | None = None
    grade: int | None = None

    for t in filtered:
        if student is None and _NAME_RE.match(t):
            student = t
            continue
        if grade is None:
            g = _coerce_grade(t)
            if g is not None:
                grade = g
                continue

    result: dict = {}
    if student is not None:
        result["student"] = student
    if grade is not None:
        result["grade"] = grade
    return result
