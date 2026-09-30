"""
LLMRouter — выбирает доступный LLM-провайдер и переключается при сбоях.

Внешний интерфейс совпадает с LLMEngine:
    chat(user_message, system_prompt) -> str

Дополнительно можно указать request_type="intent"|"response" —
тогда Router фильтрует провайдеров по supports_intent / supports_response.

Runtime-состояние провайдеров живёт ТОЛЬКО в памяти текущего запуска.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

from ..base import LLMEngine
from .network import NetworkChecker
from .provider_config import LLMProviderConfig
from .state import (
    ProviderRuntimeState, ProviderStatus, FailureReason,
)


# --- Классификация ошибок по строке ответа провайдера ---

def _classify_error(text: str) -> Optional[FailureReason]:
    """
    Провайдеры возвращают короткие безопасные строки вместо исключений
    (см. GeminiLLM._safe_error, GroqLLM._safe_error, CerebrasLLM._safe_error,
    OpenRouterLLM._safe_error). Разбираем эти строки, чтобы понять причину.
    """
    if not text:
        return None
    low = text.lower()

    # 1. Провайдер не настроен / не задан ключ / не задана модель
    #    → AUTH_ERROR (disable до перезапуска)
    if (
        "не задан api-ключ" in low
        or "не задан api ключ" in low
        or "не настроен" in low
        or "не задана модель" in low
        or "не задан ключ" in low
        or "ошибка авторизации" in low
        or "проверьте ключ" in low
    ):
        return FailureReason.AUTH_ERROR

    # 2. Quota / лимит / insufficient
    if (
        "превышен лимит" in low
        or "превышена квота" in low
        or "превышена квота" in low
        or "квота" in low
        or "quota" in low
        or "insufficient" in low
        or "resource_exhausted" in low
        or "429" in text
    ):
        return FailureReason.QUOTA_EXHAUSTED

    # 3. Rate limit (без явного quota)
    if "rate" in low and "limit" in low:
        return FailureReason.RATE_LIMITED

    # 4. Timeout
    if "время ожидания" in low or "timeout" in low or "deadline" in low:
        return FailureReason.TIMEOUT

    # 5. Network
    if (
        "нет соединения" in low
        or "network" in low
        or "unreachable" in low
        or "connect" in low
    ):
        return FailureReason.NETWORK_OFFLINE

    # 6. Модель не найдена → серверная
    if "модель не найдена" in low or "not found" in low:
        return FailureReason.SERVER_ERROR

    # 7. Пустой ответ / не удалось извлечь
    if (
        "пустой ответ" in low
        or "не удалось извлечь" in low
        or "пустой запрос" in low
    ):
        return FailureReason.INVALID_RESPONSE

    # 8. Серверные ошибки (5xx, internal)
    if (
        "ошибка запроса" in low
        or "server error" in low
        or "internal" in low
        or "500" in text
        or "502" in text
        or "503" in text
        or "504" in text
    ):
        return FailureReason.SERVER_ERROR

    return None


@dataclass
class _Entry:
    provider: LLMEngine
    config: LLMProviderConfig
    state: ProviderRuntimeState = field(default_factory=ProviderRuntimeState)


class LLMRouter(LLMEngine):
    def __init__(
        self,
        entries: list[_Entry],
        network_checker: Optional[NetworkChecker] = None,
        cooldown_seconds: float = 30.0,
    ):
        self._entries = sorted(entries, key=lambda e: e.config.priority)
        self._network = network_checker or NetworkChecker()
        self._cooldown_seconds = cooldown_seconds

    # ------------------------------------------------------------------
    def name(self) -> str:
        return "router"

    # ------------------------------------------------------------------
    def chat(self, user_message: str, system_prompt: str | None = None) -> str:
        return self._chat(user_message, system_prompt, request_type=None)

    def chat_for_intent(self, user_message: str, system_prompt: str | None = None) -> str:
        return self._chat(user_message, system_prompt, request_type="intent")

    def chat_for_response(self, user_message: str, system_prompt: str | None = None) -> str:
        return self._chat(user_message, system_prompt, request_type="response")

    # ------------------------------------------------------------------
    def _chat(
        self,
        user_message: str,
        system_prompt: Optional[str],
        request_type: Optional[str],
    ) -> str:
        print(f"[LLM Router] request={request_type or 'any'}", flush=True)

        online = self._network.is_online()
        if not online:
            print("[LLM Router] Network: OFFLINE", flush=True)

        candidates = [e for e in self._entries if self._supports(e, request_type)]
        if not candidates:
            return "LLM Router: нет подходящего провайдера для этого запроса."

        last_error_text = ""

        for entry in candidates:
            name = entry.config.name

            if not entry.state.is_usable():
                if entry.state.status == ProviderStatus.DISABLED:
                    print(
                        f"[LLM Router] {name} → SKIP (disabled: "
                        f"{entry.state.reason.value if entry.state.reason else 'unknown'})",
                        flush=True,
                    )
                else:
                    print(f"[LLM Router] {name} → SKIP (cooldown)", flush=True)
                continue

            if entry.config.requires_internet and not online:
                print(f"[LLM Router] {name} → SKIP (requires internet)", flush=True)
                continue

            print(f"[LLM Router] trying {name}", flush=True)

            answer = self._try_provider(entry, user_message, system_prompt)

            reason = _classify_error(answer)
            if reason is None:
                print(f"[LLM Router] {name} → OK", flush=True)
                return answer

            last_error_text = answer
            self._handle_failure(entry, reason)
            print(f"[LLM Router] {name} → {reason.value}", flush=True)
            continue

        if last_error_text:
            return last_error_text
        return "LLM Router: все провайдеры недоступны."

    # ------------------------------------------------------------------
    def _try_provider(
        self,
        entry: _Entry,
        user_message: str,
        system_prompt: Optional[str],
    ) -> str:
        attempt = 0
        max_attempts = max(1, entry.config.max_retries + 1)
        answer = ""

        while attempt < max_attempts:
            attempt += 1
            try:
                answer = entry.provider.chat(user_message, system_prompt) or ""
            except Exception as e:
                answer = f"{entry.config.name}: ошибка запроса ({type(e).__name__})."

            reason = _classify_error(answer)
            if reason is None:
                return answer

            if reason == FailureReason.INVALID_RESPONSE and attempt < max_attempts:
                continue

            return answer

        return answer

    # ------------------------------------------------------------------
    @staticmethod
    def _supports(entry: _Entry, request_type: Optional[str]) -> bool:
        if request_type == "intent":
            return entry.config.supports_intent
        if request_type == "response":
            return entry.config.supports_response
        return True

    # ------------------------------------------------------------------
    def _handle_failure(self, entry: _Entry, reason: FailureReason) -> None:
        name = entry.config.name

        if reason in (FailureReason.QUOTA_EXHAUSTED, FailureReason.RATE_LIMITED):
            entry.state.disable(reason)
            print(f"[LLM Router] {name} disabled for current session", flush=True)
            return

        if reason == FailureReason.AUTH_ERROR:
            entry.state.disable(reason)
            print(f"[LLM Router] {name} disabled for current session", flush=True)
            return

        if reason in (FailureReason.TIMEOUT, FailureReason.SERVER_ERROR,
                      FailureReason.NETWORK_OFFLINE):
            entry.state.cooldown(reason, self._cooldown_seconds)
            print(
                f"[LLM Router] {name} cooldown {int(self._cooldown_seconds)}s",
                flush=True,
            )
            return

        # INVALID_RESPONSE — не отключаем и не cooldown, просто следующий.
        return
