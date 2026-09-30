"""
Тесты GUI logging handler и LogView.

Проверяют:
  1. запись в logging появляется в GUI;
  2. несколько записей сохраняют порядок;
  3. копирование возвращает текст;
  4. сохранение создаёт файл с содержимым;
  5. очистка очищает отображение;
  6. отсутствие открытого окна не ломает logging;
  7. повторное открытие LogView восстанавливает real-time;
  8. логирование из worker-потока доходит до LogView.

Требуют QApplication (offscreen).
"""
import logging
import os
import sys
import threading
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


@pytest.fixture
def gui_handler(qapp, tmp_path, monkeypatch):
    import importlib
    from assistant import logging_setup

    monkeypatch.setenv("EVA_LOG_DIR", str(tmp_path))
    importlib.reload(logging_setup)

    logger = logging.getLogger("eva")
    for h in list(logger.handlers):
        logger.removeHandler(h)

    logging_setup.setup_logging(to_console=False)
    handler = logging_setup.install_gui_handler(capacity=200)
    yield handler, logging_setup

    for h in list(logger.handlers):
        try:
            h.close()
        except Exception:
            pass
        logger.removeHandler(h)


def _make_log_view(handler):
    from assistant.ui.log_view import LogView
    import assistant.logging_setup as ls
    saved = ls._gui_handler
    ls._gui_handler = handler
    try:
        return LogView()
    finally:
        ls._gui_handler = saved


# --- 1 ---
def test_log_record_appears_in_gui(gui_handler, qapp):
    handler, ls = gui_handler
    view = _make_log_view(handler)
    view.show()
    qapp.processEvents()

    log = ls.get_logger("test")
    log.info("hello-gui-marker-1")
    qapp.processEvents()

    text = view._text.toPlainText()
    assert "hello-gui-marker-1" in text

    view.close()
    view.deleteLater()


# --- 2 ---
def test_multiple_records_preserve_order(gui_handler, qapp):
    handler, ls = gui_handler
    view = _make_log_view(handler)
    view.show()
    qapp.processEvents()

    log = ls.get_logger("test")
    for i in range(5):
        log.info("order-marker-%d", i)
    qapp.processEvents()

    text = view._text.toPlainText()
    positions = [text.find(f"order-marker-{i}") for i in range(5)]
    assert all(p >= 0 for p in positions)
    assert positions == sorted(positions)

    view.close()
    view.deleteLater()


# --- 3 ---
def test_copy_returns_text(gui_handler, qapp):
    from PySide6.QtGui import QGuiApplication
    handler, ls = gui_handler
    view = _make_log_view(handler)
    view.show()
    qapp.processEvents()

    log = ls.get_logger("test")
    log.info("copy-marker")
    qapp.processEvents()

    view._on_copy()
    clip = QGuiApplication.clipboard().text()
    assert "copy-marker" in clip

    view.close()
    view.deleteLater()


# --- 4 ---
def test_save_creates_file(gui_handler, qapp, tmp_path, monkeypatch):
    handler, ls = gui_handler
    view = _make_log_view(handler)
    view.show()
    qapp.processEvents()

    log = ls.get_logger("test")
    log.info("save-marker")
    qapp.processEvents()

    out = tmp_path / "log_dump.txt"
    from PySide6.QtWidgets import QFileDialog
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName",
        staticmethod(lambda *a, **kw: (str(out), "txt")),
    )

    view._on_save()

    assert out.exists()
    content = out.read_text(encoding="utf-8")
    assert "save-marker" in content

    view.close()
    view.deleteLater()


# --- 5 ---
def test_clear_clears_display(gui_handler, qapp):
    handler, ls = gui_handler
    view = _make_log_view(handler)
    view.show()
    qapp.processEvents()

    log = ls.get_logger("test")
    log.info("clear-marker")
    qapp.processEvents()

    assert "clear-marker" in view._text.toPlainText()
    view._on_clear()
    assert view._text.toPlainText() == ""

    view.close()
    view.deleteLater()


# --- 6 ---
def test_logging_works_without_open_window(gui_handler, qapp):
    handler, ls = gui_handler

    log = ls.get_logger("test")
    log.info("no-window-marker-1")
    log.warning("no-window-marker-2")

    snapshot = handler.snapshot()
    joined = "\n".join(snapshot)
    assert "no-window-marker-1" in joined
    assert "no-window-marker-2" in joined


def test_buffer_shown_on_late_open(gui_handler, qapp):
    handler, ls = gui_handler

    log = ls.get_logger("test")
    log.info("early-marker-1")
    log.info("early-marker-2")

    view = _make_log_view(handler)
    view.show()
    qapp.processEvents()
    text = view._text.toPlainText()
    assert "early-marker-1" in text
    assert "early-marker-2" in text

    view.close()
    view.deleteLater()


# --- 7 ---
def test_reopen_after_close_resumes_realtime(gui_handler, qapp):
    """
    open → log A (появляется)
    close → log B (в буфер)
    open снова → log B из буфера + log C в real-time
    """
    handler, ls = gui_handler
    view = _make_log_view(handler)

    log = ls.get_logger("test")

    # Первое открытие.
    view.show()
    qapp.processEvents()
    log.info("first-open-marker")
    qapp.processEvents()
    assert "first-open-marker" in view._text.toPlainText()

    # Закрываем.
    view.close()
    qapp.processEvents()
    assert view._subscribed is False

    # Пишем в лог пока окно закрыто.
    log.info("while-closed-marker")
    qapp.processEvents()

    # Открываем повторно тот же объект.
    view.show()
    qapp.processEvents()
    # Запись, сделанная пока окно было закрыто, должна быть в окне
    # (за счёт заливки буфера при showEvent).
    text_after_reopen = view._text.toPlainText()
    assert "while-closed-marker" in text_after_reopen

    # Real-time после повторного открытия.
    log.info("after-reopen-marker")
    qapp.processEvents()
    assert "after-reopen-marker" in view._text.toPlainText()

    view.close()
    view.deleteLater()


# --- 8 ---
def test_logging_from_worker_thread(gui_handler, qapp):
    handler, ls = gui_handler
    view = _make_log_view(handler)
    view.show()
    qapp.processEvents()

    log = ls.get_logger("test")

    def worker():
        log.info("thread-marker-1")
        log.info("thread-marker-2")

    t = threading.Thread(target=worker)
    t.start()
    t.join(timeout=2.0)

    # Qt queued signal обрабатывается в GUI-потоке — дать шанс.
    for _ in range(50):
        qapp.processEvents()
        if "thread-marker-2" in view._text.toPlainText():
            break
        time.sleep(0.01)

    text = view._text.toPlainText()
    assert "thread-marker-1" in text
    assert "thread-marker-2" in text

    view.close()
    view.deleteLater()


def run_all():
    print("Запуск через pytest: pytest -v tools/test_gui_log_handler.py", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(run_all())
