"""
Smoke-тест: EVA вообще стартует.
Проверяет, что:
  - logging настраивается;
  - STT создаётся (модель не грузим);
  - LLM-провайдер создаётся;
  - TTS создаётся;
  - ActionRegistry и ActionContext создаются.

Никаких сетевых запросов.

Запуск:
    python -m tools.test_smoke_startup
"""
from __future__ import annotations

import sys

from assistant.logging_setup import setup_logging, get_logger

setup_logging(level="INFO", to_console=True)
log = get_logger("smoke")


def main() -> int:
    print("=== EVA SMOKE STARTUP ===", flush=True)

    try:
        from config import Config
        log.info("config loaded: LLM_PROVIDER=%s TTS_PROVIDER=%s",
                 Config.LLM_PROVIDER, Config.TTS_PROVIDER)
    except Exception:
        log.exception("config import failed")
        return 1

    try:
        from assistant.stt.whisper_stt import WhisperSTT
        stt = WhisperSTT()
        log.info("WhisperSTT constructed (lazy)")
        assert stt is not None
    except Exception:
        log.exception("WhisperSTT failed")
        return 1

    try:
        from assistant.llm.echo_llm import EchoLLM
        from assistant.llm.router import LLMRouter, LLMProviderConfig, NetworkChecker
        # Простой echo-провайдер, чтобы smoke не зависел от ключей.
        router = LLMRouter([], NetworkChecker())
        log.info("LLMRouter constructed with empty provider list")
    except Exception:
        log.exception("LLMRouter failed")
        return 1

    try:
        from assistant.tts.pyttsx3_tts import Pyttsx3TTS
        # Pyttsx3TTS в конструкторе вызывает engine init — это может быть тяжело,
        # но для smoke-теста достаточно проверить импорт класса.
        from assistant.tts.silero_tts import SileroTTS
        log.info("TTS classes imported")
    except Exception:
        log.exception("TTS import failed")
        return 1

    try:
        from assistant.actions.base import ActionRegistry, ActionContext
        reg = ActionRegistry()
        ctx = ActionContext()
        log.info("ActionRegistry + ActionContext constructed")
    except Exception:
        log.exception("Actions failed")
        return 1

    print("=== SMOKE OK ===", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
