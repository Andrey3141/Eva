"""
Тесты runtime-применения настроек через Application.

Проверяют:
  - CONFIG_CHANGED → пересоздание LLM/STT/TTS;
  - атомарность (нет состояния new LLM + old parser);
  - ошибка создания → старые компоненты остаются;
  - последовательный rebuild: pending keys не теряются;
  - снапшот Core не меняется во время уже идущего handle_audio;
  - replace_runtime_components не трогает нетронутые компоненты.

Никакого GUI, никакого sounddevice, никакого UI.
Application подменяется на минимальный контейнер.
"""
import os
import sys
import threading
import time
from unittest import mock

import numpy as np

from assistant.events import EventBus, Event, EventType


# ---------------------------------------------------------------------------
# Fake-компоненты
# ---------------------------------------------------------------------------

class FakeCore:
    """Минимальный Core для тестов _do_rebuild — без handle_audio."""

    def __init__(self):
        self.stt = "STT-OLD"
        self.intent_parser = "PARSER-OLD"
        self.response_gen = "RESP-OLD"
        self.tts = "TTS-OLD"

    def replace_runtime_components(self, components: dict) -> None:
        for name in ("stt", "intent_parser", "response_gen", "tts"):
            if name in components:
                setattr(self, name, components[name])


class FakeStateManager:
    def set(self, _state):
        pass


def _make_application(core, bus, callbacks):
    """
    Собирает минимальный Application без listener и device-сканирования.
    Подменяет ContinuousListener и device-функции, чтобы не трогать
    реальное аудио.
    """
    from assistant.ui import app as app_mod

    with mock.patch.object(app_mod, "ContinuousListener") as mock_listener, \
         mock.patch.object(app_mod, "pick_input_device", return_value=None), \
         mock.patch.object(app_mod, "_device_by_index", return_value=None):
        inst = mock_listener.return_value
        inst.set_muted = lambda *_a, **_kw: None
        inst.start = lambda: None
        inst.stop = lambda: None
        inst.close_gate = lambda *_a, **_kw: None
        inst.open_gate = lambda *_a, **_kw: None

        application = app_mod.Application(
            core=core,
            bus=bus,
            state_mgr=FakeStateManager(),
            settings_store=None,
            rebuild_callbacks=callbacks,
        )
    return application


# ---------------------------------------------------------------------------
# 1. LLM rebuild — атомарная связка
# ---------------------------------------------------------------------------

def test_llm_rebuild_replaces_parser_and_response_atomically():
    core = FakeCore()
    bus = EventBus()

    new_llm = "LLM-NEW"
    new_parser = "PARSER-NEW"
    new_resp = "RESP-NEW"

    def llm_factory():
        return new_llm

    def parsers_factory(llm):
        assert llm is new_llm
        return new_parser, new_resp

    app = _make_application(core, bus, {
        "llm": llm_factory,
        "parsers": parsers_factory,
    })

    app._do_rebuild(["LLM_PROVIDER"])

    assert core.intent_parser == new_parser
    assert core.response_gen == new_resp
    assert core.stt == "STT-OLD"
    assert core.tts == "TTS-OLD"


def test_stt_rebuild_only_touches_stt():
    core = FakeCore()
    bus = EventBus()

    def stt_factory():
        return "STT-NEW"

    app = _make_application(core, bus, {"stt": stt_factory})
    app._do_rebuild(["WHISPER_MODEL"])

    assert core.stt == "STT-NEW"
    assert core.intent_parser == "PARSER-OLD"
    assert core.response_gen == "RESP-OLD"
    assert core.tts == "TTS-OLD"


def test_tts_rebuild_only_touches_tts():
    core = FakeCore()
    bus = EventBus()

    def tts_factory():
        return "TTS-NEW"

    app = _make_application(core, bus, {"tts": tts_factory})
    app._do_rebuild(["TTS_PROVIDER"])

    assert core.tts == "TTS-NEW"
    assert core.stt == "STT-OLD"
    assert core.intent_parser == "PARSER-OLD"


# ---------------------------------------------------------------------------
# 2. Ошибки — старые компоненты живы
# ---------------------------------------------------------------------------

def test_llm_rebuild_error_keeps_old_components():
    core = FakeCore()
    bus = EventBus()

    def llm_factory():
        raise RuntimeError("no key")

    def parsers_factory(llm):
        return "PARSER-NEW", "RESP-NEW"

    app = _make_application(core, bus, {
        "llm": llm_factory,
        "parsers": parsers_factory,
    })

    raised = False
    try:
        app._do_rebuild(["LLM_PROVIDER"])
    except RuntimeError:
        raised = True

    assert raised is True
    assert core.intent_parser == "PARSER-OLD"
    assert core.response_gen == "RESP-OLD"


def test_parser_error_keeps_old_llm_state():
    core = FakeCore()
    bus = EventBus()

    def llm_factory():
        return "LLM-NEW"

    def parsers_factory(llm):
        raise RuntimeError("bad parsers")

    app = _make_application(core, bus, {
        "llm": llm_factory,
        "parsers": parsers_factory,
    })

    raised = False
    try:
        app._do_rebuild(["LLM_PROVIDER"])
    except RuntimeError:
        raised = True

    assert raised is True
    assert core.intent_parser == "PARSER-OLD"
    assert core.response_gen == "RESP-OLD"


# ---------------------------------------------------------------------------
# 3. Последовательный rebuild: pending keys не теряются
# ---------------------------------------------------------------------------

def test_pending_keys_are_processed_after_current_rebuild():
    """
    Второй CONFIG_CHANGED во время первого rebuild не теряется:
    его keys накапливаются в pending и обрабатываются после завершения
    текущего шага. Параллельных rebuild-потоков нет.
    """
    core = FakeCore()
    bus = EventBus()

    first_started = threading.Event()
    first_release = threading.Event()
    call_order = []

    def slow_stt_factory():
        call_order.append("stt-first")
        first_started.set()
        first_release.wait(timeout=2.0)
        return "STT-FIRST"

    def tts_factory():
        call_order.append("tts-second")
        return "TTS-SECOND"

    app = _make_application(core, bus, {
        "stt": slow_stt_factory,
        "tts": tts_factory,
    })

    # Первый: STT → стартует медленный rebuild.
    app._on_config_changed(Event(
        type=EventType.CONFIG_CHANGED,
        payload={"changed_keys": ["WHISPER_MODEL"]},
    ))
    assert first_started.wait(timeout=1.0), "первый rebuild не стартовал"

    # Второй: TTS → должен накопиться в pending.
    app._on_config_changed(Event(
        type=EventType.CONFIG_CHANGED,
        payload={"changed_keys": ["TTS_PROVIDER"]},
    ))

    # Отпускаем первый rebuild.
    first_release.set()

    # Ждём завершения цепочки.
    for _ in range(100):
        if core.stt == "STT-FIRST" and core.tts == "TTS-SECOND":
            break
        time.sleep(0.02)

    assert core.stt == "STT-FIRST", f"stt={core.stt}"
    assert core.tts == "TTS-SECOND", f"tts={core.tts}"
    assert call_order == ["stt-first", "tts-second"], call_order


def test_same_key_pending_is_processed_again():
    """
    Если во время rebuild прилетит тот же ключ — он тоже должен быть
    обработан после завершения текущего шага.
    """
    core = FakeCore()
    bus = EventBus()

    first_started = threading.Event()
    first_release = threading.Event()
    calls = []

    def stt_factory():
        calls.append("stt")
        if len(calls) == 1:
            first_started.set()
            first_release.wait(timeout=2.0)
        return f"STT-CALL-{len(calls)}"

    app = _make_application(core, bus, {"stt": stt_factory})

    app._on_config_changed(Event(
        type=EventType.CONFIG_CHANGED,
        payload={"changed_keys": ["WHISPER_MODEL"]},
    ))
    assert first_started.wait(timeout=1.0)

    # Тот же ключ — должен накопиться.
    app._on_config_changed(Event(
        type=EventType.CONFIG_CHANGED,
        payload={"changed_keys": ["WHISPER_MODEL"]},
    ))

    first_release.set()

    for _ in range(100):
        if core.stt == "STT-CALL-2":
            break
        time.sleep(0.02)

    assert core.stt == "STT-CALL-2", f"stt={core.stt}"
    assert len(calls) == 2, calls


# ---------------------------------------------------------------------------
# 4. CONFIG_CHANGED через EventBus → фоновый rebuild
# ---------------------------------------------------------------------------

def test_config_changed_event_triggers_background_rebuild():
    core = FakeCore()
    bus = EventBus()

    def stt_factory():
        return "STT-FROM-EVENT"

    app = _make_application(core, bus, {"stt": stt_factory})

    bus.publish(Event(
        type=EventType.CONFIG_CHANGED,
        payload={"changed_keys": ["WHISPER_MODEL"]},
    ))

    for _ in range(50):
        if core.stt == "STT-FROM-EVENT":
            break
        time.sleep(0.02)

    assert core.stt == "STT-FROM-EVENT"


def test_config_changed_with_non_rebuild_keys_is_noop():
    core = FakeCore()
    bus = EventBus()

    app = _make_application(core, bus, {})

    bus.publish(Event(
        type=EventType.CONFIG_CHANGED,
        payload={"changed_keys": ["ASSISTANT_NAME", "UI_VOLUME"]},
    ))
    time.sleep(0.1)

    assert core.stt == "STT-OLD"
    assert core.intent_parser == "PARSER-OLD"
    assert core.response_gen == "RESP-OLD"
    assert core.tts == "TTS-OLD"


# ---------------------------------------------------------------------------
# 5. Снапшот Core
# ---------------------------------------------------------------------------

def test_runtime_snapshot_is_consistent_during_handle_audio():
    from assistant.core import AssistantCore
    from assistant.wake.base import WakeDetector, WakeResult
    from assistant.intent.base import IntentParser, Intent
    from assistant.response.base import ResponseGenerator
    from assistant.actions.base import ActionRegistry, ActionContext
    from assistant.confirmation.base import (
        ConfirmationParser, ConfirmationDecision,
    )
    from assistant.stt.base import STTEngine
    from assistant.tts.base import TTSEngine

    class BlockingSTT(STTEngine):
        def __init__(self, name):
            self.name = name
            self.transcribe_started = threading.Event()
            self.release = threading.Event()

        def transcribe(self, audio, sample_rate):
            self.transcribe_started.set()
            self.release.wait(timeout=2.0)
            return f"hello-from-{self.name}"

    class _Wake(WakeDetector):
        def detect(self, text):
            return WakeResult(True, text)

    class _Parser(IntentParser):
        def parse(self, cmd):
            return [Intent(name="answer", params={}, confidence=0.9, raw_text=cmd)]

    class _Resp(ResponseGenerator):
        def generate(self, cmd, intent, action_result=None):
            return f"RESP[{cmd}]"

    class _Conf(ConfirmationParser):
        def parse(self, text):
            return ConfirmationDecision.UNKNOWN

    class _TTS(TTSEngine):
        def speak(self, text):
            pass

    old_stt = BlockingSTT("OLD")
    new_stt = BlockingSTT("NEW")

    core = AssistantCore(
        stt=old_stt,
        wake=_Wake(),
        intent_parser=_Parser(),
        response_gen=_Resp(),
        actions=ActionRegistry(),
        tts=_TTS(),
        confirmation_parser=_Conf(),
        context=ActionContext(addressed_to_assistant=True),
    )

    result_holder = {}

    def worker():
        result_holder["r"] = core.handle_audio(
            np.zeros(16000, dtype="float32"), 16000,
        )

    t = threading.Thread(target=worker)
    t.start()

    assert old_stt.transcribe_started.wait(timeout=1.0), "transcribe не стартовал"

    core.replace_runtime_components({"stt": new_stt})
    assert core.stt is new_stt

    old_stt.release.set()
    t.join(timeout=2.0)

    r = result_holder["r"]
    assert "hello-from-OLD" in r.recognized_text
    assert "RESP[hello-from-OLD]" in r.final_speech


def test_replace_runtime_components_preserves_untouched():
    from assistant.core import AssistantCore
    from assistant.wake.base import WakeDetector, WakeResult
    from assistant.intent.base import IntentParser
    from assistant.response.base import ResponseGenerator
    from assistant.actions.base import ActionRegistry, ActionContext
    from assistant.confirmation.base import (
        ConfirmationParser, ConfirmationDecision,
    )
    from assistant.stt.base import STTEngine
    from assistant.tts.base import TTSEngine

    class _STT(STTEngine):
        def __init__(self, name):
            self.name = name

        def transcribe(self, audio, sample_rate):
            return ""

    class _Wake(WakeDetector):
        def detect(self, text):
            return WakeResult(False, text)

    class _Parser(IntentParser):
        def parse(self, cmd):
            return []

    class _Resp(ResponseGenerator):
        def generate(self, cmd, intent, action_result=None):
            return ""

    class _Conf(ConfirmationParser):
        def parse(self, text):
            return ConfirmationDecision.UNKNOWN

    class _TTS(TTSEngine):
        def speak(self, text):
            pass

    stt_old = _STT("stt-old")
    tts_old = _TTS()
    parser_old = _Parser()
    resp_old = _Resp()

    core = AssistantCore(
        stt=stt_old,
        wake=_Wake(),
        intent_parser=parser_old,
        response_gen=resp_old,
        actions=ActionRegistry(),
        tts=tts_old,
        confirmation_parser=_Conf(),
        context=ActionContext(),
    )

    stt_new = _STT("stt-new")
    core.replace_runtime_components({"stt": stt_new})

    assert core.stt is stt_new
    assert core.tts is tts_old
    assert core.intent_parser is parser_old
    assert core.response_gen is resp_old


# ---------------------------------------------------------------------------
# Прямой запуск
# ---------------------------------------------------------------------------

def run_all():
    tests = [
        test_llm_rebuild_replaces_parser_and_response_atomically,
        test_stt_rebuild_only_touches_stt,
        test_tts_rebuild_only_touches_tts,
        test_llm_rebuild_error_keeps_old_components,
        test_parser_error_keeps_old_llm_state,
        test_pending_keys_are_processed_after_current_rebuild,
        test_same_key_pending_is_processed_again,
        test_config_changed_event_triggers_background_rebuild,
        test_config_changed_with_non_rebuild_keys_is_noop,
        test_runtime_snapshot_is_consistent_during_handle_audio,
        test_replace_runtime_components_preserves_untouched,
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
    print()
    print(f"=== {len(tests) - failed}/{len(tests)} RUNTIME TESTS PASSED (direct) ===", flush=True)
    return failed


def main():
    if not os.path.exists("assistant"):
        print("Запускать из корня проекта.", flush=True)
        sys.exit(2)
    sys.exit(1 if run_all() else 0)


if __name__ == "__main__":
    main()
