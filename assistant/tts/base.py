from abc import ABC, abstractmethod


class TTSEngine(ABC):
    @abstractmethod
    def speak(self, text: str) -> None:
        ...
