from abc import ABC, abstractmethod
from ..intent.base import Intent


class ResponseGenerator(ABC):
    """Превращает намерение в человеческий текст для TTS."""

    @abstractmethod
    def generate(self, user_command: str, intent: Intent, action_result: str | None = None) -> str:
        ...
