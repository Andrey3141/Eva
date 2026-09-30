"""
LLM-провайдер Gemini для EVA.

Интерфейс совпадает с LLMEngine:
    chat(user_message: str, system_prompt: str | None) -> str

Ключ берётся только из .env (GEMINI_API_KEY). В логах не выводится.
Модель задаётся через GEMINI_MODEL (по умолчанию gemini-3.1-flash-lite).

Ошибки не пробрасываются наружу как traceback — возвращается
безопасная строка, которую EVA может озвучить.
"""
from __future__ import annotations

import os

from .base import LLMEngine

try:
    from google import genai
    from google.genai import types as genai_types
    _GENAI_AVAILABLE = True
except Exception:
    genai = None
    genai_types = None
    _GENAI_AVAILABLE = False


DEFAULT_MODEL = "gemini-3.1-flash-lite"


class GeminiLLM(LLMEngine):
    """
    Gemini через официальный SDK google-genai.
    - ключ: только из окружения (GEMINI_API_KEY)
    - модель: из окружения (GEMINI_MODEL)
    - безопасный fallback на ошибки
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
    ):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "").strip()
        self.model = model or os.getenv("GEMINI_MODEL", DEFAULT_MODEL)

        self._client = None

        if not _GENAI_AVAILABLE:
            print(
                "[LLM] Gemini: пакет google-genai не установлен. "
                "Установите: pip install google-genai",
                flush=True,
            )
            return

        if not self.api_key:
            print(
                "[LLM] Gemini: GEMINI_API_KEY не задан. "
                "Проверьте .env.",
                flush=True,
            )
            return

        try:
            # Клиент создаётся без вывода ключа в лог.
            self._client = genai.Client(api_key=self.api_key)
            print(
                f"[LLM] Gemini готов: model={self.model}",
                flush=True,
            )
        except Exception as e:
            print(f"[LLM] Gemini: ошибка инициализации клиента: {e}", flush=True)
            self._client = None

    # ------------------------------------------------------------------
    def name(self) -> str:
        return "gemini"

    # ------------------------------------------------------------------
    def chat(self, user_message: str, system_prompt: str | None = None) -> str:
        # 1. Проверки конфигурации
        if not _GENAI_AVAILABLE:
            return "Gemini недоступен: не установлен пакет google-genai."

        if self._client is None:
            if not self.api_key:
                return "Gemini не настроен: не задан API-ключ."
            return "Gemini не настроен: клиент не инициализирован."

        if not user_message or not user_message.strip():
            return "Пустой запрос."

        # 2. Формируем контент
        #    Системный промпт передаём через system_instruction, если задан.
        try:
            contents = [
                genai_types.Content(
                    role="user",
                    parts=[genai_types.Part(text=user_message)],
                )
            ]
            config = None
            if system_prompt:
                config = genai_types.GenerateContentConfig(
                    system_instruction=system_prompt,
                )
        except Exception:
            # Если SDK другой версии и types недоступны — упрощённый путь.
            contents = user_message
            config = None

        # 3. Запрос
        try:
            if config is not None:
                response = self._client.models.generate_content(
                    model=self.model,
                    contents=contents,
                    config=config,
                )
            else:
                response = self._client.models.generate_content(
                    model=self.model,
                    contents=contents,
                )
        except Exception as e:
            return self._safe_error(e)

        # 4. Извлечение текста
        try:
            text = self._extract_text(response)
        except Exception as e:
            return self._safe_error(e)

        if not text:
            return "Gemini вернул пустой ответ."

        return text.strip()

    # ------------------------------------------------------------------
    @staticmethod
    def _extract_text(response) -> str:
        """
        Достаём текст из ответа SDK. Поддерживаем оба варианта:
        response.text (короткий путь) и response.candidates[*].content.parts[*].text.
        """
        # короткий путь
        try:
            t = getattr(response, "text", None)
            if t:
                return str(t)
        except Exception:
            pass

        # полный путь
        try:
            candidates = getattr(response, "candidates", None) or []
            out_parts: list[str] = []
            for cand in candidates:
                content = getattr(cand, "content", None)
                if content is None:
                    continue
                parts = getattr(content, "parts", None) or []
                for p in parts:
                    txt = getattr(p, "text", None)
                    if txt:
                        out_parts.append(str(txt))
            return "\n".join(out_parts).strip()
        except Exception:
            return ""

    # ------------------------------------------------------------------
    @staticmethod
    def _safe_error(e: Exception) -> str:
        """
        Превращаем исключение SDK в понятную короткую строку.
        Без traceback, без утечки ключа.
        """
        name = type(e).__name__
        msg = str(e)

        low = msg.lower()

        if "quota" in low or "rate" in low or "429" in msg:
            return "Gemini: превышен лимит запросов. Попробуйте позже."
        if "api key" in low or "unauthor" in low or "permission" in low or "401" in msg or "403" in msg:
            return "Gemini: ошибка авторизации. Проверьте ключ."
        if "timeout" in low or "deadline" in low:
            return "Gemini: превышено время ожидания ответа."
        if "network" in low or "connect" in low or "unreachable" in low:
            return "Gemini: нет соединения с сервером."
        if "not found" in low or "404" in msg:
            return f"Gemini: модель не найдена ({name})."
        return f"Gemini: ошибка запроса ({name})."
