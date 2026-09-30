import re
from .base import WakeDetector, WakeResult


class KeywordWakeDetector(WakeDetector):
    """
    Детектор обращения по алиасам.

    Источники алиасов (в порядке приоритета):
      1. явные aliases, переданные в конструктор;
      2. Config.ASSISTANT_ALIASES;
      3. Config.ASSISTANT_NAME.

    Итоговый набор = ASSISTANT_ALIASES + ASSISTANT_NAME (без дублей).
    Если ASSISTANT_ALIASES пуст — используется только ASSISTANT_NAME.

    ВАЖНО: Config читается через `import config` на каждом detect(),
    а не через `from config import Config`. Прямая ссылка кэширует
    класс Config, и после `importlib.reload(config)` в тестах/рантайме
    детектор видел бы старый класс. Через модуль — всегда актуальный.
    """

    def __init__(self, aliases: list[str] | None = None):
        self._static_aliases = (
            [a.lower() for a in aliases] if aliases is not None else None
        )

    def _aliases(self) -> list[str]:
        if self._static_aliases is not None:
            return list(self._static_aliases)

        import config
        C = config.Config

        aliases: list[str] = []
        for a in (C.ASSISTANT_ALIASES or []):
            a_norm = str(a).strip().lower()
            if a_norm and a_norm not in aliases:
                aliases.append(a_norm)

        name = (C.ASSISTANT_NAME or "").strip().lower()
        if name and name not in aliases:
            aliases.append(name)

        return aliases

    def detect(self, text: str) -> WakeResult:
        if not text:
            return WakeResult(False, text)

        low = text.lower().strip()
        for alias in self._aliases():
            pattern = rf"(^|[\s,]){re.escape(alias)}(\b|[\s,])"
            m = re.search(pattern, low)
            if m:
                start, end = m.span()
                cleaned = (text[:start] + text[end:]).strip(" ,.!?-—")
                return WakeResult(True, cleaned or text)

        return WakeResult(False, text)
