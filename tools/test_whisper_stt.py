"""
Регрессионные тесты для assistant.stt.whisper_stt.WhisperSTT.

Проверяют контракт обёртки, а НЕ загрузку реальной модели:
  - модель не создаётся в __init__ (ленивая загрузка);
  - при первом обращении используется Config.WHISPER_MODEL;
  - передаются device="cpu" и compute_type="int8";
  - модель создаётся ровно один раз;
  - ошибка загрузки модели не маскируется;
  - transcribe передаёт language, beam_size, vad_filter и склеивает сегменты;
  - модуль не требует интернета сам по себе (без реального скачивания).

Запуск через pytest:
    pytest -v tools/test_whisper_stt.py
Прямой запуск:
    python -m tools.test_whisper_stt

Никакой сети, никакой загрузки модели.
"""
import os
import sys
import threading
from types import SimpleNamespace
from unittest import mock

import numpy as np

from assistant.stt import whisper_stt as whisper_stt_module
from assistant.stt.whisper_stt import WhisperSTT


# ---------------------------------------------------------------------------
# Хелперы
# ---------------------------------------------------------------------------

class _FakeWhisperModel:
    """
    Заменяет faster_whisper.WhisperModel.
    Считает вызовы конструктора, хранит аргументы, отдаёт контролируемые сегменты.
    """
    instances: list["_FakeWhisperModel"] = []

    def __init__(self, model_size, device=None, compute_type=None, **kwargs):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.kwargs = kwargs
        self.transcribe_calls: list[dict] = []
        self.segments_to_return: list = []
        _FakeWhisperModel.instances.append(self)

    def transcribe(self, audio, **kwargs):
        self.transcribe_calls.append({"audio": audio, **kwargs})
        return (iter(self.segments_to_return), {"language": "ru"})


def _reset_fake():
    _FakeWhisperModel.instances.clear()


def _patch_whisper_model():
    """
    Подменяет WhisperModel в модуле whisper_stt на наш fake-класс.
    Возвращает контекстный менеджер.
    """
    return mock.patch.object(whisper_stt_module, "WhisperModel", _FakeWhisperModel)


def _fake_config(model_size="small", language="ru"):
    """Возвращает объект, который по интерфейсу совпадает с Config."""
    return SimpleNamespace(
        WHISPER_MODEL=model_size,
        WHISPER_LANGUAGE=language,
    )


# ---------------------------------------------------------------------------
# 1. Ленивая загрузка: модель не создаётся в __init__
# ---------------------------------------------------------------------------

def test_init_does_not_create_model():
    _reset_fake()
    with _patch_whisper_model():
        stt = WhisperSTT(model_size="small", language="ru")
        assert _FakeWhisperModel.instances == [], (
            "WhisperModel не должен создаваться в __init__"
        )
        assert stt.is_loaded is False


def test_model_created_on_first_transcribe():
    _reset_fake()
    with _patch_whisper_model():
        stt = WhisperSTT(model_size="small", language="ru")
        assert _FakeWhisperModel.instances == []

        stt.transcribe(np.zeros(16000, dtype="float32"), 16000)

        assert len(_FakeWhisperModel.instances) == 1
        assert stt.is_loaded is True


# ---------------------------------------------------------------------------
# 2. Model size / device / compute_type передаются в WhisperModel
# ---------------------------------------------------------------------------

def test_model_size_used_from_config(monkeypatch):
    _reset_fake()
    fake_cfg = _fake_config(model_size="small")
    monkeypatch.setattr(whisper_stt_module, "Config", fake_cfg)

    with _patch_whisper_model():
        stt = WhisperSTT()  # без явного model_size — берём из Config
        stt.transcribe(np.zeros(16000, dtype="float32"), 16000)

    assert _FakeWhisperModel.instances[0].model_size == "small"


def test_explicit_model_size_overrides_config(monkeypatch):
    _reset_fake()
    fake_cfg = _fake_config(model_size="small")
    monkeypatch.setattr(whisper_stt_module, "Config", fake_cfg)

    with _patch_whisper_model():
        stt = WhisperSTT(model_size="base")
        stt.transcribe(np.zeros(16000, dtype="float32"), 16000)

    assert _FakeWhisperModel.instances[0].model_size == "base"


def test_device_and_compute_type_passed():
    _reset_fake()
    with _patch_whisper_model():
        stt = WhisperSTT(model_size="small", language="ru",
                         device="cpu", compute_type="int8")
        stt.transcribe(np.zeros(16000, dtype="float32"), 16000)

    inst = _FakeWhisperModel.instances[0]
    assert inst.device == "cpu", inst.device
    assert inst.compute_type == "int8", inst.compute_type


# ---------------------------------------------------------------------------
# 3. Модель создаётся ровно один раз
# ---------------------------------------------------------------------------

def test_model_created_only_once():
    _reset_fake()
    with _patch_whisper_model():
        stt = WhisperSTT(model_size="small", language="ru")
        stt.transcribe(np.zeros(16000, dtype="float32"), 16000)
        stt.transcribe(np.zeros(16000, dtype="float32"), 16000)
        stt.transcribe(np.zeros(16000, dtype="float32"), 16000)

    assert len(_FakeWhisperModel.instances) == 1, (
        f"Ожидался 1 экземпляр WhisperModel, получено {len(_FakeWhisperModel.instances)}"
    )


def test_concurrent_first_transcribe_creates_single_model():
    """
    Двойная проверка (double-checked locking) должна создать модель один раз
    даже при одновременном вызове из нескольких потоков.
    """
    _reset_fake()
    with _patch_whisper_model():
        stt = WhisperSTT(model_size="small", language="ru")

        def worker():
            stt.transcribe(np.zeros(16000, dtype="float32"), 16000)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    assert len(_FakeWhisperModel.instances) == 1, (
        f"Ожидался 1 экземпляр, получено {len(_FakeWhisperModel.instances)}"
    )


# ---------------------------------------------------------------------------
# 4. Ошибка загрузки модели не маскируется
# ---------------------------------------------------------------------------

def test_model_load_error_propagates():
    _reset_fake()

    class _BrokenWhisperModel:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("cannot load model")

    with mock.patch.object(whisper_stt_module, "WhisperModel", _BrokenWhisperModel):
        stt = WhisperSTT(model_size="small", language="ru")
        raised = False
        try:
            stt.transcribe(np.zeros(16000, dtype="float32"), 16000)
        except RuntimeError as e:
            raised = True
            assert "cannot load model" in str(e)

    assert raised is True, "Ошибка WhisperModel должна пробрасываться наружу"


# ---------------------------------------------------------------------------
# 5. transcribe: параметры и склейка сегментов
# ---------------------------------------------------------------------------

def test_transcribe_passes_language_beam_vad():
    _reset_fake()
    with _patch_whisper_model():
        stt = WhisperSTT(model_size="small", language="ru")
        stt.transcribe(np.zeros(16000, dtype="float32"), 16000)

    call = _FakeWhisperModel.instances[0].transcribe_calls[0]
    assert call.get("language") == "ru"
    assert call.get("beam_size") == 5
    assert call.get("vad_filter") is True


def test_transcribe_joins_segments():
    _reset_fake()
    with _patch_whisper_model():
        stt = WhisperSTT(model_size="small", language="ru")
        # Готовим сегменты заранее
        stt_instance_holder = {}

        # Создаём фейковую модель вручную, чтобы подложить сегменты
        class _M(_FakeWhisperModel):
            def __init__(self, *a, **kw):
                super().__init__(*a, **kw)
                self.segments_to_return = [
                    SimpleNamespace(text=" Привет,"),
                    SimpleNamespace(text=" мир."),
                ]

        with mock.patch.object(whisper_stt_module, "WhisperModel", _M):
            stt2 = WhisperSTT(model_size="small", language="ru")
            out = stt2.transcribe(np.zeros(16000, dtype="float32"), 16000)

    assert out == "Привет, мир."


# ---------------------------------------------------------------------------
# 6. Регрессия: нет интернет-вызовов при инициализации
# ---------------------------------------------------------------------------

def test_init_does_not_require_network():
    """
    Сам факт создания WhisperSTT и вызов _ensure_model (с замоканным
    WhisperModel) не должен выполнять никаких сетевых вызовов.

    Мы гарантируем это структурно: без замоканного WhisperModel модуль
    ничего не тянет из сети — реальные сетевые обращения делает только
    faster_whisper.WhisperModel, который здесь подменён.
    """
    import socket

    _reset_fake()
    original_socket = socket.socket

    def _forbidden_socket(*a, **kw):
        raise AssertionError(
            "WhisperSTT.__init__ / _ensure_model не должны открывать сокеты"
        )

    socket.socket = _forbidden_socket
    try:
        with _patch_whisper_model():
            stt = WhisperSTT(model_size="small", language="ru")
            stt._ensure_model()  # использует наш fake WhisperModel
            stt.transcribe(np.zeros(16000, dtype="float32"), 16000)
    finally:
        socket.socket = original_socket

    assert stt.is_loaded is True


# ---------------------------------------------------------------------------
# Прямой запуск
# ---------------------------------------------------------------------------

def _run_all():
    tests = [
        test_init_does_not_create_model,
        test_model_created_on_first_transcribe,
        test_device_and_compute_type_passed,
        test_model_created_only_once,
        test_model_load_error_propagates,
        test_transcribe_passes_language_beam_vad,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"[OK] {t.__name__}", flush=True)
        except AssertionError as e:
            failed += 1
            print(f"[FAIL] {t.__name__}: {e}", flush=True)
        except Exception as e:
            failed += 1
            print(f"[ERROR] {t.__name__}: {type(e).__name__}: {e}", flush=True)
    print(flush=True)
    print(f"=== {len(tests) - failed}/{len(tests)} WHISPER TESTS PASSED (direct) ===", flush=True)
    return failed


def main():
    if not os.path.exists("assistant"):
        print("Запускать из корня проекта.", flush=True)
        sys.exit(2)
    sys.exit(1 if _run_all() else 0)


if __name__ == "__main__":
    main()
