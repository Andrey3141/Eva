from openai import OpenAI
from .base import LLMEngine
from config import Config


class DeepSeekLLM(LLMEngine):
    def __init__(self):
        if not Config.DEEPSEEK_API_KEY:
            raise RuntimeError("DEEPSEEK_API_KEY не задан. Установите LLM_PROVIDER=echo для отладки.")
        self.client = OpenAI(api_key=Config.DEEPSEEK_API_KEY, base_url=Config.DEEPSEEK_BASE_URL)
        self.model = Config.DEEPSEEK_MODEL

    def chat(self, user_message: str, system_prompt: str | None = None) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_message})
        resp = self.client.chat.completions.create(
            model=self.model, messages=messages, temperature=0.2, max_tokens=512,
        )
        return resp.choices[0].message.content.strip()
