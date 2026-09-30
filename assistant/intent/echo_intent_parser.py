import re

from .base import Intent, IntentParser


class EchoIntentParser(IntentParser):
    """
    Офлайн-парсер для отладки без API.
    На этом шаге распознаёт только:
        answer       — любая фраза, не подходящая под команду;
        grade_student — "<Фамилия> <2..5>" (с необязательным глаголом).

    Составные команды пока не поддерживаются — архитектура к ним готова,
    но парсер их не создаёт.
    """

    _GRADE_WORDS = {
        "два": 2, "двойка": 2, "двойку": 2,
        "три": 3, "тройка": 3, "тройку": 3,
        "четыре": 4, "четвёрка": 4, "четверка": 4,
        "четвёрку": 4, "четверку": 4,
        "пять": 5, "пятёрка": 5, "пятерка": 5,
        "пятёрку": 5, "пятерку": 5,
    }
    _GRADE_WORD_RE = "|".join(_GRADE_WORDS.keys())

    _GRADE_CMD = re.compile(
        r"(?:(?:постав[ьи]|дай|вкати|вл[ея]пи|выстав[ьи])\s+)?"
        r"(?P<student>[А-ЯЁA-Z][а-яёa-z\-]+)\s+"
        r"(?:оценку\s+)?"
        r"(?:(?P<grade_digit>[2-5])|(?P<grade_word>" + _GRADE_WORD_RE + r"))\b",
        re.IGNORECASE,
    )

    _NEXT_SLIDE = re.compile(r"(?:следующий|дальше)\s+слайд", re.IGNORECASE)

    def parse(self, user_command: str) -> list[Intent]:
        cmd = (user_command or "").strip()
        if not cmd:
            return [Intent(name="answer", params={}, confidence=0.5, raw_text="")]

        low = cmd.lower()

        # next_slide
        if self._NEXT_SLIDE.search(low):
            return [Intent(
                name="next_slide",
                params={},
                confidence=0.97,
                raw_text=cmd,
            )]

        # grade_student
        m = self._GRADE_CMD.search(cmd)
        if m:
            grade = self._extract_grade(m)
            if grade is not None:
                return [Intent(
                    name="grade_student",
                    params={
                        "student": m.group("student"),
                        "grade": grade,
                    },
                    confidence=0.96,
                    raw_text=cmd,
                )]
            # Оценка есть, но вне 2..5 — не угадываем.
            return [Intent(name="answer", params={}, confidence=0.4, raw_text=cmd)]

        # Всё остальное — answer.
        return [Intent(name="answer", params={}, confidence=0.6, raw_text=cmd)]

    # ------------------------------------------------------------------
    def _extract_grade(self, m: re.Match) -> int | None:
        digit = m.groupdict().get("grade_digit")
        if digit:
            try:
                v = int(digit)
                if v in (2, 3, 4, 5):
                    return v
            except ValueError:
                return None

        word = m.groupdict().get("grade_word")
        if word:
            return self._GRADE_WORDS.get(word.lower())

        return None
