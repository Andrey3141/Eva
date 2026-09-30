"""
Groq LLM-провайдер для EVA.
Использует OpenAI-совместимый API Groq.
Ключ и модель — только из .env. В логи не выводятся.

Интерфейс совпадает с LLMEngine:
    chat(user_message: str, system_prompt: str | None) -> str
"""
from __future__ import annotations

import os

from openai import OpenAI

from .base import LLMEngine


DEFAULT_BASE_URL = "https://api.groq.com/openai/v1"


class GroqLLM(LLMEngine):
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
    ):
        self.api_key = api_key or os.getenv("GROQ_API_KEY", "").strip()
        self.model = model or os.getenv("GROQ_MODEL", "").strip()
        self.base_url = base_url or os.getenv("GROQ_BASE_URL", DEFAULT_BASE_URL)

        self._client = None

        if not self.api_key:
            print(
                "[LLM] Groq: GROQ_API_KEY не задан. Проверьте .env.",
                flush=True,
            )
            return

        if not self.model:
            print(
                "[LLM] Groq: GROQ_MODEL не задан. Проверьте .env.",
                flush=True,
            )
            return

        try:
            self._client = OpenAI(api_key=self.api_key, base_url=self.base_url)
            print(f"[LLM] Groq готов: model={self.model}", flush=True)
        except Exception as e:
            print(f"[LLM] Groq: ошибка инициализации клиента: {e}", flush=True)
            self._client = None

    def name(self) -> str:
        return "groq"

    def chat(self, user_message: str, system_prompt: str | None = None) -> str:
        if self._client is None:
            if not self.api_key:
                return "Groq не настроен: не задан API-ключ."
            if not self.model:
                return "Groq не настроен: не задана модель."
            return "Groq не настроен: клиент не инициализирован."

        if not user_message or not user_message.strip():
            return "Пустой запрос."

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_message})

        try:
            resp = self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.2,
                max_tokens=1024,
            )
        except Exception as e:
            return self._safe_error(e)

        try:
            text = resp.choices[0].message.content or ""
        except Exception:
            return "Groq: не удалось извлечь текст ответа."

        text = text.strip()
        if not text:
            return "Groq вернул пустой ответ."
        return text

    @staticmethod
    def _safe_error(e: Exception) -> str:
        name = type(e).__name__
        msg = str(e)
        low = msg.lower()

        if "quota" in low or "insufficient" in low:
            return "Groq: превышена квота."
        if "rate" in low or "429" in msg:
            return "Groq: превышен лимит запросов."
        if "unauthor" in low or "permission" in low or "401" in msg or "403" in msg:
            return "Groq: ошибка авторизации. Проверьте ключ."
        if "timeout" in low or "deadline" in low:
            return "Groq: превышено время ожидания ответа."
        if "network" in low or "connect" in low or "unreachable" in low:
            return "Groq: нет соединения с сервером."
        if "not found" in low or "404" in msg:
            return f"Groq: модель не найдена ({name})."
        return f"Groq: ошибка запроса ({name})."
