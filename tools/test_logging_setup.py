"""
Тесты assistant.logging_setup — фактический контракт.

Запуск через pytest:
    pytest -v tools/test_logging_setup.py
Прямой запуск:
    python -m tools.test_logging_setup

Тесты:
  - не обращаются в интернет;
  - не запускают Whisper / TTS / GUI;
  - используют только фиктивные секреты;
  - не трогают реальный .env и production config.
"""
import importlib
import logging
import os
import re
import sys
import threading
from pathlib import Path

import pytest

from assistant import logging_setup
from assistant import paths


# ===========================================================================
# Изоляция: каждый тест получает чистый logging_setup и изолированный log_dir
# ===========================================================================

@pytest.fixture
def fresh_logging(tmp_path, monkeypatch):
    """
    Даёт изолированный лог-каталог и перезагруженный logging_setup.
    После теста — восстанавливает исходное состояние root-логгера 'eva'.
    """
    log_dir = tmp_path / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("EVA_LOG_DIR", str(log_dir))

    # Сносим все handlers с логгера 'eva' и его детей — на всякий случай.
    _clear_eva_logger()

    importlib.reload(logging_setup)

    yield log_dir

    _clear_eva_logger()


def _clear_eva_logger():
    logger = logging.getLogger("eva")
    for h in list(logger.handlers):
        try:
            h.close()
        except Exception:
            pass
        logger.removeHandler(h)


# ===========================================================================
# 1. setup_logging создаёт лог-файл
# ===========================================================================

def test_setup_creates_log_file(fresh_logging):
    log_path = logging_setup.setup_logging(to_console=False)
    assert isinstance(log_path, Path)
    assert log_path.exists()
    assert log_path.is_file()


# ===========================================================================
# 2. Имя файла соответствует eva_YYYY-MM-DD_HH-MM-SS.log
# ===========================================================================

def test_log_filename_format(fresh_logging):
    log_path = logging_setup.setup_logging(to_console=False)
    name = log_path.name
    assert re.match(r"^eva_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}\.log$", name), name


# ===========================================================================
# 3. EVA_LOG_DIR реально меняет каталог
# ===========================================================================

def test_log_dir_from_env(fresh_logging):
    log_path = logging_setup.setup_logging(to_console=False)
    assert log_path.parent == fresh_logging


# ===========================================================================
# 4. EVA_LOG_LEVEL реально меняет уровень
# ===========================================================================

def test_log_level_from_env(fresh_logging, monkeypatch):
    monkeypatch.setenv("EVA_LOG_LEVEL", "WARNING")
    importlib.reload(logging_setup)
    log_path = logging_setup.setup_logging(to_console=False)

    logger = logging.getLogger("eva")
    assert logger.level == logging.WARNING


# ===========================================================================
# 5. DEBUG пишется при уровне DEBUG
# ===========================================================================

def test_debug_written_at_debug_level(fresh_logging, monkeypatch):
    monkeypatch.setenv("EVA_LOG_LEVEL", "DEBUG")
    importlib.reload(logging_setup)
    log_path = logging_setup.setup_logging(to_console=False)

    log = logging_setup.get_logger("test")
    log.debug("hello-debug-msg")

    _flush_eva_logger()
    content = log_path.read_text(encoding="utf-8")
    assert "hello-debug-msg" in content


# ===========================================================================
# 6. DEBUG не пишется при уровне INFO
# ===========================================================================

def test_debug_not_written_at_info_level(fresh_logging, monkeypatch):
    monkeypatch.setenv("EVA_LOG_LEVEL", "INFO")
    importlib.reload(logging_setup)
    log_path = logging_setup.setup_logging(to_console=False)

    log = logging_setup.get_logger("test")
    log.debug("should-not-appear-debug")
    log.info("should-appear-info")

    _flush_eva_logger()
    content = log_path.read_text(encoding="utf-8")
    assert "should-not-appear-debug" not in content
    assert "should-appear-info" in content


# ===========================================================================
# 7. INFO / WARNING / ERROR пишутся
# ===========================================================================

def test_info_warning_error_written(fresh_logging, monkeypatch):
    monkeypatch.setenv("EVA_LOG_LEVEL", "DEBUG")
    importlib.reload(logging_setup)
    log_path = logging_setup.setup_logging(to_console=False)

    log = logging_setup.get_logger("test")
    log.info("msg-info")
    log.warning("msg-warning")
    log.error("msg-error")

    _flush_eva_logger()
    content = log_path.read_text(encoding="utf-8")
    assert "msg-info" in content
    assert "msg-warning" in content
    assert "msg-error" in content


# ===========================================================================
# 8. to_console=False не создаёт StreamHandler для console
# ===========================================================================

def test_no_console_handler_when_disabled(fresh_logging):
    logging_setup.setup_logging(to_console=False)
    logger = logging.getLogger("eva")

    for h in logger.handlers:
        assert not isinstance(h, logging.StreamHandler) or isinstance(h, logging.FileHandler), \
            f"Unexpected StreamHandler: {h}"


# ===========================================================================
# 9. Повторный setup_logging не создаёт дублирующие handlers
# ===========================================================================

def test_repeated_setup_does_not_duplicate_handlers(fresh_logging):
    logging_setup.setup_logging(to_console=False)
    logger = logging.getLogger("eva")
    n1 = len(logger.handlers)

    logging_setup.setup_logging(to_console=False)
    n2 = len(logger.handlers)

    assert n2 == n1, f"handlers duplicated: {n1} -> {n2}"


# ===========================================================================
# 10. Повторная запись не дублируется
# ===========================================================================

def test_no_duplicate_records(fresh_logging):
    log_path = logging_setup.setup_logging(to_console=False)
    logging_setup.setup_logging(to_console=False)  # повторный вызов

    log = logging_setup.get_logger("test")
    log.info("unique-message-xyz")

    _flush_eva_logger()
    content = log_path.read_text(encoding="utf-8")
    assert content.count("unique-message-xyz") == 1, content


# ===========================================================================
# 11. API-ключ не появляется в файле
# ===========================================================================

def test_api_key_not_logged(fresh_logging):
    log_path = logging_setup.setup_logging(to_console=False)
    log = logging_setup.get_logger("test")

    fake_gemini = "fake-gemini-secret-123"
    fake_openrouter = "fake-openrouter-secret-456"
    fake_deepseek = "fake-deepseek-secret-789"

    log.info("GEMINI_API_KEY=%s", fake_gemini)
    log.info("OPENROUTER_API_KEY=%s", fake_openrouter)
    log.info("DEEPSEEK_API_KEY=%s", fake_deepseek)

    _flush_eva_logger()
    content = log_path.read_text(encoding="utf-8")

    # Ни одной части фиктивных ключей не должно быть
    for frag in ("fake-gemini-secret", "fake-openrouter-secret",
                 "fake-deepseek-secret", "123", "456", "789"):
        # "123" и т. п. слишком короткие — проверим именно полные фрагменты.
        if len(frag) > 5:
            assert frag not in content, f"leaked: {frag}"


# ===========================================================================
# 12. Bearer-токен не появляется в файле
# ===========================================================================

def test_bearer_token_not_logged(fresh_logging):
    log_path = logging_setup.setup_logging(to_console=False)
    log = logging_setup.get_logger("test")

    log.info("Authorization: Bearer fake-bearer-token-789")

    _flush_eva_logger()
    content = log_path.read_text(encoding="utf-8")
    assert "fake-bearer-token-789" not in content


# ===========================================================================
# 13. sys.excepthook логирует необработанное исключение
# ===========================================================================

def test_sys_excepthook_logs_unhandled(fresh_logging, monkeypatch):
    log_path = logging_setup.setup_logging(to_console=False)
    logging_setup.install_exception_hooks()

    # Ловим stdout/stderr, чтобы pytest не пугался.
    monkeypatch.setattr(sys, "stderr", open(os.devnull, "w"))

    try:
        raise RuntimeError("unhandled-exception-marker-abc")
    except RuntimeError:
        exc_type, exc_value, exc_tb = sys.exc_info()
        sys.excepthook(exc_type, exc_value, exc_tb)

    _flush_eva_logger()
    content = log_path.read_text(encoding="utf-8")
    assert "unhandled-exception-marker-abc" in content
    assert "RuntimeError" in content


# ===========================================================================
# 14. threading.excepthook логирует необработанное исключение потока
# ===========================================================================

def test_threading_excepthook_logs_unhandled(fresh_logging):
    log_path = logging_setup.setup_logging(to_console=False)
    logging_setup.install_exception_hooks()

    def worker():
        raise RuntimeError("thread-exception-marker-xyz")

    t = threading.Thread(target=worker, name="eva-test-thread")
    t.start()
    t.join()

    _flush_eva_logger()
    content = log_path.read_text(encoding="utf-8")
    assert "thread-exception-marker-xyz" in content
    assert "RuntimeError" in content


# ===========================================================================
# 15. Логирование не зависит от cwd
# ===========================================================================

def test_logging_does_not_depend_on_cwd(fresh_logging, tmp_path, monkeypatch):
    log_path = logging_setup.setup_logging(to_console=False)
    log = logging_setup.get_logger("test")

    other = tmp_path / "other"
    other.mkdir()
    monkeypatch.chdir(other)
    log.info("cwd-independent-marker")

    _flush_eva_logger()
    content = log_path.read_text(encoding="utf-8")
    assert "cwd-independent-marker" in content


# ===========================================================================
# Helpers
# ===========================================================================

def _flush_eva_logger():
    logger = logging.getLogger("eva")
    for h in logger.handlers:
        try:
            h.flush()
        except Exception:
            pass


# ===========================================================================
# Прямой запуск
# ===========================================================================

def _run_all():
    tests = [
        test_setup_creates_log_file,
        test_log_filename_format,
    ]
    failed = 0
    for t in tests:
        try:
            # В прямом запуске используем временный каталог через tempfile.
            import tempfile
            tmp = Path(tempfile.mkdtemp(prefix="eva_log_test_"))
            os.environ["EVA_LOG_DIR"] = str(tmp)
            importlib.reload(logging_setup)
            t(tmp)
            print(f"[OK] {t.__name__}", flush=True)
        except AssertionError as e:
            failed += 1
            print(f"[FAIL] {t.__name__}: {e}", flush=True)
        except Exception as e:
            failed += 1
            print(f"[ERROR] {t.__name__}: {type(e).__name__}: {e}", flush=True)
    print(flush=True)
    print(f"=== {len(tests) - failed}/{len(tests)} LOGGING TESTS PASSED (direct) ===", flush=True)
    return failed


def main():
    if not os.path.exists("assistant"):
        print("Запускать из корня проекта.", flush=True)
        sys.exit(2)
    sys.exit(1 if _run_all() else 0)


if __name__ == "__main__":
    main()
