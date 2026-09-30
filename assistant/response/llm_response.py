from .base import ResponseGenerator
from ..intent.base import Intent
from ..llm.base import LLMEngine


SYSTEM_PROMPT = (
    "Ты — голосовой ассистент преподавателя. Ответь кратко (1–2 предложения), "
    "по-русски, дружелюбно. Не добавляй JSON, только текст для озвучки."
)


class LLMResponseGenerator(ResponseGenerator):
    def __init__(self, llm: LLMEngine):
        self.llm = llm

    def generate(self, user_command: str, intent: Intent, action_result: str | None = None) -> str:
        if intent.is_action():
            # для действий — короткая форма
            if action_result:
                return action_result
            return f"Выполняю: {intent.name}."

        prompt = (
            f"Пользователь сказал: «{user_command}».\n"
            f"Ответь как ассистент преподавателя."
        )
        return self.llm.chat(prompt, SYSTEM_PROMPT)
