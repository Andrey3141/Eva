from abc import ABC, abstractmethod
from enum import Enum


class ConfirmationDecision(str, Enum):
    YES = "yes"
    NO = "no"
    UNKNOWN = "unknown"


class ConfirmationParser(ABC):
    """
    Понимает короткий ответ пользователя в контексте подтверждения.
    Не используется для общего распознавания речи — только
    в окне ожидания ответа на конкретный вопрос.
    """

    @abstractmethod
    def parse(self, text: str) -> ConfirmationDecision:
        ...
