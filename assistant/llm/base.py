from abc import ABC, abstractmethod


class LLMEngine(ABC):
    @abstractmethod
    def chat(self, user_message: str, system_prompt: str | None = None) -> str:
        ...

    def name(self) -> str:
        return self.__class__.__name__
