from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class WakeResult:
    is_addressed: bool
    cleaned_text: str


class WakeDetector(ABC):
    @abstractmethod
    def detect(self, text: str) -> WakeResult:
        ...
