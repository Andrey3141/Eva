import re
from .base import ConfirmationDecision, ConfirmationParser


class KeywordConfirmationParser(ConfirmationParser):
    """
    Простой парсер подтверждения по ключевым словам.
    Работает с короткими фразами: "да", "ага", "не надо", "отмена" и т.п.
    """

    YES_PATTERNS = [
        r"\bда\b",
        r"\bага\b",
        r"\bугу\b",
        r"\bконечно\b",
        r"\bподтверждаю\b",
        r"\bподтвердить\b",
        r"\bвыполняй\b",
        r"\bставь\b",
        r"\bставьте\b",
        r"\bдавай\b",
        r"\bхорошо\b",
        r"\bок\b",
        r"\bокей\b",
    ]

    NO_PATTERNS = [
        r"\bнет\b",
        r"\bне\s+надо\b",
        r"\bне\s+ставь\b",
        r"\bне\s+ставьте\b",
        r"\bотмена\b",
        r"\bотменить\b",
        r"\bотменяй\b",
        r"\bстоп\b",
    ]

    def parse(self, text: str) -> ConfirmationDecision:
        if not text:
            return ConfirmationDecision.UNKNOWN

        low = text.lower().strip()

        for pat in self.NO_PATTERNS:
            if re.search(pat, low):
                return ConfirmationDecision.NO

        for pat in self.YES_PATTERNS:
            if re.search(pat, low):
                return ConfirmationDecision.YES

        return ConfirmationDecision.UNKNOWN
