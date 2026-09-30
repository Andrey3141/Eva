from .base import LLMEngine


class EchoLLM(LLMEngine):
    """Заглушка. Не используется в основном пайплайне (Intent/Response сами по себе)."""
    def chat(self, user_message: str, system_prompt: str | None = None) -> str:
        return user_message
