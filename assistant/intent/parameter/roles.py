"""
Роли параметров, эталонные подписи для embedding-скорера
и типовые валидаторы значений.

roles.py — нижний уровень. Не импортирует другие модули пакета
(ml_slot_tagger, embedding_candidate_scorer, fusion, router).

MLSlotTagger — это token classification + span grouping, не BIO.
"""
from __future__ import annotations

import re
from enum import Enum
from typing import Callable, Optional


class Role(str, Enum):
    O = "O"
    COMMAND = "COMMAND"
    OBJECT = "OBJECT"
    TOPIC = "TOPIC"
    STUDENT = "STUDENT"
    GRADE = "GRADE"


INTENT_PARAM_SCHEMA: dict[str, dict[str, Role]] = {
    "open_presentation": {"topic": Role.TOPIC},
    "open_video": {"topic": Role.TOPIC},
    "open_excel": {"topic": Role.TOPIC},
    "grade_student": {"student": Role.STUDENT, "grade": Role.GRADE},
    "next_slide": {},
    "answer": {},
    "close_presentation": {},
    "close_video": {},
    "close_file": {},
    "close_excel": {},
    "restart_presentation": {},
    "restart_excel": {},
}


ROLE_SIGNATURES: dict[Role, list[str]] = {
    Role.TOPIC: [
        "тема доклада",
        "тема презентации",
        "о чём материал",
        "предмет обсуждения",
        "тема занятия",
        "название темы",
    ],
    Role.STUDENT: [
        "фамилия ученика",
        "имя студента",
        "учащийся школы",
        "фио ученика",
    ],
    Role.GRADE: [
        "оценка ученика",
        "балл за работу",
        "отметка в журнале",
    ],
    Role.OBJECT: [
        "объект действия",
        "цель команды",
        "что открыть",
    ],
    Role.COMMAND: [
        "команда",
        "приказ",
        "действие ассистента",
    ],
}


# ---------------------------------------------------------------------------
# Служебные множества
# ---------------------------------------------------------------------------

_TOPIC_MARKERS: set[str] = {
    "про", "по", "об", "о", "обо",
    "на", "тему", "темой", "теме",
    "насчёт", "насчет", "касательно", "относительно",
}

_COMMAND_WORDS: set[str] = {
    "открой", "открыть", "покажи", "показать",
    "запусти", "запустить", "включи", "включить",
    "воспроизведи", "воспроизвести",
    "поставь", "поставить", "выставь", "выставить",
    "дай", "дать", "запиши", "записать", "проставь", "проставить",
    "переключи", "переключить", "перейди", "перейти",
    "дальше", "вперёд", "вперед", "следующий", "следующая",
}

_OBJECT_WORDS: set[str] = {
    "презентацию", "презентация", "презентации",
    "слайды", "слайд", "слайдов",
    "видео", "видеозапись", "ролик", "ролики", "фильм",
    "материал", "материалы", "документ", "документы",
    "файл", "файлы", "таблицу", "таблица",
}

_GRADE_WORDS: dict[str, int] = {
    "два": 2, "двойка": 2, "двойку": 2, "двойке": 2,
    "три": 3, "тройка": 3, "тройку": 3, "тройке": 3,
    "четыре": 4, "четвёрка": 4, "четверка": 4,
    "четвёрку": 4, "четверку": 4,
    "пять": 5, "пятёрка": 5, "пятерка": 5,
    "пятёрку": 5, "пятерку": 5,
    "шесть": 6, "шестёрка": 6, "шестерка": 6,
    "семь": 7, "семёрка": 7, "семерка": 7,
    "восемь": 8, "восьмёрка": 8, "восьмерка": 8,
    "девять": 9, "девятка": 9,
    "десять": 10, "десятка": 10,
    "один": 1, "единица": 1,
}


# ---------------------------------------------------------------------------
# Публичные хелперы
# ---------------------------------------------------------------------------

def is_stopword_token(value: str) -> bool:
    low = (value or "").strip().lower()
    if not low:
        return True
    return (low in _TOPIC_MARKERS
            or low in _COMMAND_WORDS
            or low in _OBJECT_WORDS)


def is_topic_marker(value: str) -> bool:
    return (value or "").strip().lower() in _TOPIC_MARKERS


def is_command_word(value: str) -> bool:
    return (value or "").strip().lower() in _COMMAND_WORDS


def is_object_word(value: str) -> bool:
    return (value or "").strip().lower() in _OBJECT_WORDS


def coerce_grade(value) -> Optional[int]:
    if isinstance(value, int):
        return value
    s = str(value or "").strip().lower()
    if not s:
        return None
    if s.isdigit():
        try:
            return int(s)
        except ValueError:
            return None
    return _GRADE_WORDS.get(s)


_INT_RE = re.compile(r"^-?\d+$")


def _is_valid_grade(value: str) -> bool:
    g = coerce_grade(value)
    return g is not None and 1 <= g <= 10


def _is_valid_student(value: str) -> bool:
    s = str(value or "").strip()
    if not s:
        return False
    low = s.lower()
    if low in _COMMAND_WORDS or low in _OBJECT_WORDS or low in _TOPIC_MARKERS:
        return False
    if _INT_RE.match(s):
        return False
    if not any(ch.isalpha() for ch in s):
        return False
    if len(s.split()) > 4:
        return False
    return True


def _is_valid_topic(value: str) -> bool:
    s = str(value or "").strip()
    if not s:
        return False
    low = s.lower()
    if low in _TOPIC_MARKERS or low in _COMMAND_WORDS or low in _OBJECT_WORDS:
        return False
    if _INT_RE.match(s):
        return False
    tokens = [t for t in low.split() if t]
    if not tokens:
        return False
    content_tokens = [
        t for t in tokens
        if t not in _TOPIC_MARKERS
        and t not in _COMMAND_WORDS
        and t not in _OBJECT_WORDS
    ]
    return bool(content_tokens)


TYPE_VALIDATORS: dict[str, Callable[[str], bool]] = {
    "grade": _is_valid_grade,
    "student": _is_valid_student,
    "topic": _is_valid_topic,
}


def passes_type(param_name: str, value: str) -> bool:
    validator = TYPE_VALIDATORS.get(param_name)
    if validator is None:
        return True
    return validator(value)
