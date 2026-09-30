"""
Централизованное логирование EVA.

- Один файл на запуск: <logs_dir>/eva_YYYY-MM-DD_HH-MM-SS.log
- Уровень: EVA_LOG_LEVEL (по умолчанию DEBUG).
- Формат: timestamp | level | module | message
- Никакие API-ключи/токены/пароли в лог не попадают.
- sys.excepthook и threading.excepthook пишут полный traceback в файл.
- Дублирование в консоль (stdout) сохраняется.
- GUI-логирование: отдельный handler (GuiLogHandler) копит последние
  записи в буфере и эмитит Qt-сигнал new_line. Терминальный и файловый
  handler'ы продолжают работать независимо.
"""
from __future__ import annotations

import logging
import os
import platform
import sys
import threading
import traceback
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Optional

from assistant import paths


_LOGGER_NAME = "eva"
_initialized = False
_log_file_path: Optional[Path] = None
_gui_handler: Optional["GuiLogHandler"] = None


# --- Фильтр, вырезающий секреты из сообщений ---

_SECRET_MARKERS = (
    "api_key", "apikey", "api-key",
    "token", "password", "passwd",
    "secret", "authorization",
    "bearer ",
)


class _SecretFilter(logging.Filter):
    """
    Защита от случайного попадания ключа в лог.
    Маскирует длинные токены (sk-..., gsk_..., or-..., Bearer ...).
    """

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = str(record.getMessage())
            low = msg.lower()
            if any(m in low for m in _SECRET_MARKERS):
                import re
                record.msg = re.sub(
                    r"([A-Za-z0-9_\-]{20,})",
                    "***",
                    msg,
                )
                record.args = ()
        except Exception:
            pass
        return True


# ---------------------------------------------------------------------------
# GUI handler
# ---------------------------------------------------------------------------

class _SignalBridge:
    """
    Ленивая обёртка над Qt-сигналом. Импортируется только если
    действительно используется GUI.
    """


def _make_gui_handler_class():
    """
    Создаёт класс GuiLogHandler с наследованием от QObject и logging.Handler.
    Импорт PySide6 — ленивый, чтобы logging_setup не тянул Qt в CLI-режиме.
    """
    from PySide6.QtCore import QObject, Signal

    class GuiLogHandler(QObject, logging.Handler):
        """
        Handler, который:
          - копит последние записи в ring buffer (deque);
          - при emit эмитит Qt-сигнал new_line(str) — потокобезопасно,
            т.к. Qt queued connection сам перекинет вызов в GUI-поток;
          - если окно не подписано, буфер всё равно пополняется.
        """

        new_line = Signal(str)

        def __init__(self, capacity: int = 2000, level=logging.NOTSET):
            QObject.__init__(self)
            logging.Handler.__init__(self, level=level)
            self._buffer: deque[str] = deque(maxlen=capacity)
            self.setFormatter(logging.Formatter(
                fmt="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
                datefmt="%H:%M:%S",
            ))

        # ------------------------------------------------------------------
        def emit(self, record: logging.LogRecord) -> None:
            try:
                line = self.format(record)
            except Exception:
                self.handleError(record)
                return
            self._buffer.append(line)
            try:
                self.new_line.emit(line)
            except Exception:
                # Если Qt уже пришиблен — не падаем.
                pass

        # ------------------------------------------------------------------
        def snapshot(self) -> list[str]:
            """Возвращает копию буфера (для заливки при открытии окна)."""
            return list(self._buffer)

        def clear_buffer(self) -> None:
            self._buffer.clear()

    return GuiLogHandler


GuiLogHandler = None  # заполняется при install_gui_handler


# --- Инициализация ---

def setup_logging(
    level: Optional[str] = None,
    log_dir: Optional[str] = None,
    to_console: bool = True,
) -> Path:
    """
    Создаёт файловый лог для текущего запуска EVA и настраивает root logger.
    Возвращает путь к созданному файлу.

    GUI-хендлер НЕ создаётся здесь. Он устанавливается отдельно через
    install_gui_handler(), чтобы logging_setup не тянул PySide6 в CLI-режиме.
    """
    global _initialized, _log_file_path
    if _initialized and _log_file_path is not None:
        return _log_file_path

    lvl_name = (level or os.getenv("EVA_LOG_LEVEL", "DEBUG")).upper()
    lvl = getattr(logging, lvl_name, logging.DEBUG)

    base_dir = Path(log_dir) if log_dir else paths.logs_dir()
    base_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_path = base_dir / f"eva_{ts}.log"

    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(lvl)
    logger.propagate = False

    for h in list(logger.handlers):
        logger.removeHandler(h)

    fmt = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    fh = logging.FileHandler(log_path, mode="a", encoding="utf-8")
    fh.setLevel(lvl)
    fh.setFormatter(fmt)
    fh.addFilter(_SecretFilter())
    logger.addHandler(fh)

    if to_console:
        ch = logging.StreamHandler(stream=sys.stdout)
        ch.setLevel(lvl)
        ch.setFormatter(fmt)
        ch.addFilter(_SecretFilter())
        logger.addHandler(ch)

    _initialized = True
    _log_file_path = log_path

    logger.info("=== EVA START ===")
    logger.info("Python %s", sys.version.replace("\n", " "))
    logger.info("Executable %s", sys.executable)
    logger.info("Platform %s", platform.platform())
    logger.info("CWD %s", os.getcwd())
    logger.info("Log file %s", log_path)
    logger.info("Log level %s (%s)", lvl_name, logging.getLevelName(lvl))
    return log_path


def install_gui_handler(capacity: int = 2000) -> "GuiLogHandler":
    """
    Создаёт и подключает GUI-хендлер к логгеру 'eva'.
    Идемпотентно: повторный вызов возвращает тот же handler.

    Может быть вызван из GUI-потока после создания QApplication.
    Если вызвать до setup_logging — handler всё равно будет создан
    и попадёт на логгер; но обычно порядок: setup_logging → install_gui_handler.
    """
    global _gui_handler
    if _gui_handler is not None:
        return _gui_handler

    cls = _make_gui_handler_class()
    handler = cls(capacity=capacity)
    handler.setLevel(logging.DEBUG)
    handler.addFilter(_SecretFilter())

    logger = logging.getLogger(_LOGGER_NAME)
    logger.addHandler(handler)

    _gui_handler = handler
    return handler


def get_gui_handler() -> Optional["GuiLogHandler"]:
    return _gui_handler


# --- Хелперы для получения логгеров по модулю ---

def get_logger(module: str) -> logging.Logger:
    return logging.getLogger(f"{_LOGGER_NAME}.{module}")


# --- Глобальные перехватчики исключений ---

def install_exception_hooks() -> None:
    logger = get_logger("excepthook")

    def _sys_hook(exc_type, exc_value, exc_tb):
        try:
            logger.error(
                "Unhandled exception in main thread:\n%s",
                "".join(traceback.format_exception(exc_type, exc_value, exc_tb)),
            )
        except Exception:
            pass
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    def _thread_hook(args):
        try:
            logger.error(
                "Unhandled exception in thread '%s':\n%s",
                args.thread.name if args.thread else "<unknown>",
                "".join(traceback.format_exception(
                    args.exc_type, args.exc_value, args.exc_traceback)),
            )
        except Exception:
            pass

    sys.excepthook = _sys_hook
    try:
        threading.excepthook = _thread_hook
    except Exception:
        pass


def current_log_path() -> Optional[Path]:
    return _log_file_path


def log_config_summary(config) -> None:
    logger = get_logger("config")
    try:
        logger.info("LLM_PROVIDER=%s", getattr(config, "LLM_PROVIDER", "?"))
        logger.info("GEMINI_MODEL=%s", getattr(config, "GEMINI_MODEL", "?"))
        logger.info(
            "GEMINI_API_KEY=%s",
            "<set>" if getattr(config, "GEMINI_API_KEY", "") else "<empty>",
        )
        logger.info("GROQ_MODEL=%s", getattr(config, "GROQ_MODEL", "?"))
        logger.info(
            "GROQ_API_KEY=%s",
            "<set>" if getattr(config, "GROQ_API_KEY", "") else "<empty>",
        )
        logger.info("CEREBRAS_MODEL=%s", getattr(config, "CEREBRAS_MODEL", "?"))
        logger.info(
            "CEREBRAS_API_KEY=%s",
            "<set>" if getattr(config, "CEREBRAS_API_KEY", "") else "<empty>",
        )
        logger.info("OPENROUTER_MODEL=%s", getattr(config, "OPENROUTER_MODEL", "?"))
        logger.info(
            "OPENROUTER_API_KEY=%s",
            "<set>" if getattr(config, "OPENROUTER_API_KEY", "") else "<empty>",
        )
        logger.info(
            "DEEPSEEK_API_KEY=%s",
            "<set>" if getattr(config, "DEEPSEEK_API_KEY", "") else "<empty>",
        )
        logger.info("ASSISTANT_NAME=%s", getattr(config, "ASSISTANT_NAME", "?"))
        logger.info("ASSISTANT_ALIASES=%s", getattr(config, "ASSISTANT_ALIASES", "?"))
        logger.info("TTS_PROVIDER=%s", getattr(config, "TTS_PROVIDER", "?"))
        logger.info("SILERO_SPEAKER=%s", getattr(config, "SILERO_SPEAKER", "?"))
        logger.info("WHISPER_MODEL=%s", getattr(config, "WHISPER_MODEL", "?"))
        logger.info("WHISPER_LANGUAGE=%s", getattr(config, "WHISPER_LANGUAGE", "?"))
    except Exception as e:
        logger.warning("config summary error: %s", e)
