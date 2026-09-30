from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class Intent:
    name: str = "unknown"           # answer | grade_student | open_file | next_slide | unknown
    params: dict = field(default_factory=dict)
    confidence: float = 0.0
    raw_text: str = ""

    def is_action(self) -> bool:
        return self.name not in ("answer", "unknown", "none", "")


class IntentParser(ABC):
    """
    Преобразует исходную команду пользователя в СПИСОК намерений.
    На этом шаге — обычно один элемент; архитектура сразу допускает
    несколько (для будущих составных команд).
    """

    @abstractmethod
    def parse(self, user_command: str) -> list[Intent]:
        ...

    def parse_one(self, user_command: str) -> Intent:
        """Удобная обёртка: вернуть первое намерение или answer."""
        items = self.parse(user_command)
        return items[0] if items else Intent(name="answer", raw_text=user_command)
