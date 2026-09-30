"""
Диагностический запуск WhisperSTT.
Ничего не меняет в EVA, только загружает модель и печатает состояние.

Запуск:
    python -m tools.test_whisper_startup
    python -X faulthandler -m tools.test_whisper_startup
"""
from __future__ import annotations

import os
import sys
import time
import traceback
from pathlib import Path

# 0. faulthandler включаем как можно раньше, чтобы поймать возможный segfault.
try:
    import faulthandler
    faulthandler.enable()
except Exception:
    pass


def env_state():
    print("=== WHISPER STARTUP DIAGNOSTIC ===", flush=True)
    print(f"PID: {os.getpid()}", flush=True)
    print(f"Python: {sys.version.split()[0]} ({sys.executable})", flush=True)
    print(f"Platform: {sys.platform}", flush=True)
    print(f"CWD: {Path.cwd()}", flush=True)

    # Версии библиотек
    try:
        import faster_whisper
        print(f"faster_whisper: {getattr(faster_whisper, '__version__', 'unknown')}",
              flush=True)
    except Exception as e:
        print(f"faster_whisper import error: {e}", flush=True)

    try:
        import ctranslate2
        print(f"ctranslate2: {getattr(ctranslate2, '__version__', 'unknown')}",
              flush=True)
    except Exception as e:
        print(f"ctranslate2 import error: {e}", flush=True)

    try:
        import numpy
        print(f"numpy: {numpy.__version__}", flush=True)
    except Exception as e:
        print(f"numpy import error: {e}", flush=True)

    # Сетевые переменные
    print("--- proxy / network env ---", flush=True)
    for key in (
        "HTTP_PROXY", "http_proxy",
        "HTTPS_PROXY", "https_proxy",
        "ALL_PROXY", "all_proxy",
        "NO_PROXY", "no_proxy",
        "HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE",
        "HF_HOME", "XDG_CACHE_HOME",
    ):
        v = os.environ.get(key)
        print(f"  {key} = {v!r}", flush=True)

    # Пути к возможным кэшам моделей
    try:
        from config import Config
        print(f"WHISPER_MODEL (config): {Config.WHISPER_MODEL}", flush=True)
        print(f"WHISPER_LANGUAGE (config): {Config.WHISPER_LANGUAGE}", flush=True)
    except Exception as e:
        print(f"config import error: {e}", flush=True)


def load_whisper():
    print("", flush=True)
    print("--- importing WhisperSTT ---", flush=True)
    try:
        from assistant.stt.whisper_stt import WhisperSTT
        print("WhisperSTT import: OK", flush=True)
    except Exception:
        print("WhisperSTT import: FAILED", flush=True)
        traceback.print_exc()
        return 1

    print("", flush=True)
    print("--- constructing WhisperSTT (lazy: model not loaded yet) ---", flush=True)
    try:
        stt = WhisperSTT()
        print("WhisperSTT constructed: OK", flush=True)
    except Exception:
        print("WhisperSTT constructor: FAILED", flush=True)
        traceback.print_exc()
        return 1

    print("", flush=True)
    print("--- BEFORE WhisperModel load (_ensure_model) ---", flush=True)
    t0 = time.time()

    try:
        # Вызываем то же самое, что делает transcribe() при первом обращении.
        stt._ensure_model()
        dt = time.time() - t0
        print(f"--- AFTER WhisperModel load: OK (took {dt:.2f}s) ---",
              flush=True)
    except Exception:
        print("--- WhisperModel load: FAILED ---", flush=True)
        traceback.print_exc()
        return 1

    print("", flush=True)
    print("=== WHISPER STARTUP: OK ===", flush=True)
    return 0


def main() -> int:
    env_state()
    return load_whisper()


if __name__ == "__main__":
    sys.exit(main())
