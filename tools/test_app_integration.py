"""
Smoke-тест интеграционного слоя EVA.

Два независимых уровня:

  A. Unit smoke Core — ручная сборка Core с fake-зависимостями.
  B. Factory integration — реальные фабрики main.py:
     build_llm, build_parsers, build_tts, build_actions, build_context.

ИЗОЛЯЦИЯ STUBS:

  Подмена sys.modules выполняется только внутри фикстуры module_stubs
  и гарантированно восстанавливается через try/finally.

  ВАЖНО: stub `assistant.audio` ДОЛЖЕН содержать атрибут `playback`
  (модуль с play_wav/play_mp3/play), потому что production
  `assistant/tts/edge_tts.py` и `assistant/tts/silero_tts.py`
  делают `from assistant.audio import playback` на уровне модуля.

СТАТИЧЕСКАЯ ПРОВЕРКА:

  test_c_no_playwright_in_production_modules НЕ импортирует production-модули.
  Проверка идёт по исходным .py-файлам через Path("assistant").rglob("*.py").
  Никаких sys.modules, Qt, stubs и загрязнения pytest-сессии.

Запуск через pytest:
    pytest -v tools/test_app_integration.py
Прямой запуск:
    python -m tools.test_app_integration
"""
from __future__ import annotations

import os
import sys
import types
from pathlib import Path
from unittest import mock

import numpy as np
import pytest


# ===========================================================================
# Имена модулей, которые подменяются в тестах.
# ===========================================================================

_STUBBED_MODULE_NAMES = (
    "assistant.audio",
    "assistant.audio.device",
    "assistant.audio.recorder",
    "assistant.audio.playback",
    "assistant.stt.whisper_stt",
    "assistant.llm.deepseek_llm",
    "assistant.tts.edge_tts",
    "assistant.tts.silero_tts",
    "assistant.tts.pyttsx3_tts",
    "assistant.tts.fallback_tts",
    "PySide6",
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "edge_tts",
    "pyttsx3",
    "sounddevice",
    "faster_whisper",
    "openai",
)


# ===========================================================================
# Заглушки Qt и внешних модулей
# ===========================================================================

class _DummyQt:
    def __init__(self, *args, **kwargs):
        pass

    def __call__(self, *args, **kwargs):
        return self

    def __getattr__(self, item):
        return _DummyQt()

    def __or__(self, other):
        return self

    def __and__(self, other):
        return self


def _make_qt_module(name: str) -> types.ModuleType:
    m = types.ModuleType(name)

    explicit = (
        "QObject", "QTimer", "Signal", "Qt", "QSize", "QUrl",
        "QColor", "QPainter", "QPen", "QFont", "QPixmap", "QMovie",
        "QPalette", "QRadialGradient", "QBrush", "InputEvent",
        "QRectF", "QEasingCurve", "QPropertyAnimation",
        "Property", "QGraphicsOpacityEffect",
        "QWidget", "QLabel", "QPushButton", "QVBoxLayout", "QHBoxLayout",
        "QFormLayout", "QDialog", "QLineEdit", "QComboBox", "QCheckBox",
        "QSpinBox", "QDoubleSpinBox", "QScrollArea", "QFrame",
        "QSizePolicy", "QMainWindow", "QApplication", "QStackedLayout",
        "QToolButton", "QMenu", "QAction", "QSpacerItem",
    )
    for attr in explicit:
        setattr(m, attr, type(attr, (_DummyQt,), {}))

    def _getattr(item):
        return _DummyQt

    m.__getattr__ = _getattr
    return m


def _build_stub_modules() -> dict[str, types.ModuleType]:
    stubs: dict[str, types.ModuleType] = {}

    # --- assistant.audio.playback ---
    playback_mod = types.ModuleType("assistant.audio.playback")

    def _noop_play_wav(path):
        playback_mod.last_play_wav = path

    def _noop_play_mp3(path):
        playback_mod.last_play_mp3 = path

    def _noop_play(path):
        playback_mod.last_play = path

    playback_mod.play_wav = _noop_play_wav
    playback_mod.play_mp3 = _noop_play_mp3
    playback_mod.play = _noop_play
    playback_mod.last_play_wav = None
    playback_mod.last_play_mp3 = None
    playback_mod.last_play = None
    stubs["assistant.audio.playback"] = playback_mod

    # --- assistant.audio ---
    audio_mod = types.ModuleType("assistant.audio")
    audio_mod.__path__ = []

    class _FakeAudioRecorder:
        def __init__(self, *args, **kwargs):
            self.started = False

        def start(self, *args, **kwargs):
            self.started = True

        def stop(self, *args, **kwargs):
            self.started = False

        def record(self, *args, **kwargs):
            return b""

    def _list_input_devices(*args, **kwargs):
        return []

    def _pick_input_device(*args, **kwargs):
        return None

    def _describe_device(*args, **kwargs):
        return "fake audio device"

    audio_mod.AudioRecorder = _FakeAudioRecorder
    audio_mod.list_input_devices = _list_input_devices
    audio_mod.pick_input_device = _pick_input_device
    audio_mod.describe_device = _describe_device
    audio_mod.playback = playback_mod
    stubs["assistant.audio"] = audio_mod

    # --- assistant.audio.device ---
    audio_device_mod = types.ModuleType("assistant.audio.device")
    audio_device_mod.list_input_devices = _list_input_devices
    stubs["assistant.audio.device"] = audio_device_mod

    # --- assistant.audio.recorder ---
    audio_recorder_mod = types.ModuleType("assistant.audio.recorder")
    audio_recorder_mod.AudioRecorder = _FakeAudioRecorder
    stubs["assistant.audio.recorder"] = audio_recorder_mod

    # --- assistant.stt.whisper_stt ---
    whisper_mod = types.ModuleType("assistant.stt.whisper_stt")

    class _FakeWhisperSTT:
        def __init__(self, *args, **kwargs):
            pass

        def transcribe(self, audio, sample_rate):
            return ""

        def _ensure_model(self):
            return None

    whisper_mod.WhisperSTT = _FakeWhisperSTT
    stubs["assistant.stt.whisper_stt"] = whisper_mod

    # --- assistant.llm.deepseek_llm ---
    deepseek_mod = types.ModuleType("assistant.llm.deepseek_llm")

    class _FakeDeepSeekLLM:
        def __init__(self, *args, **kwargs):
            pass

        def chat(self, user_message, system_prompt=None):
            return "fake-answer"

        def name(self):
            return "fake-deepseek"

    deepseek_mod.DeepSeekLLM = _FakeDeepSeekLLM
    stubs["assistant.llm.deepseek_llm"] = deepseek_mod

    # --- assistant.tts.edge_tts ---
    edge_tts_stub = types.ModuleType("assistant.tts.edge_tts")

    class _FakeEdgeTTS:
        def __init__(self, *args, **kwargs):
            pass

        def speak(self, text):
            pass

        def stop(self):
            pass

    edge_tts_stub.EdgeTTS = _FakeEdgeTTS
    stubs["assistant.tts.edge_tts"] = edge_tts_stub

    # --- assistant.tts.silero_tts ---
    silero_stub = types.ModuleType("assistant.tts.silero_tts")

    class _FakeSileroTTS:
        def __init__(self, *args, **kwargs):
            pass

        def speak(self, text):
            pass

        def stop(self):
            pass

    silero_stub.SileroTTS = _FakeSileroTTS
    stubs["assistant.tts.silero_tts"] = silero_stub

    # --- assistant.tts.pyttsx3_tts ---
    pyttsx_stub = types.ModuleType("assistant.tts.pyttsx3_tts")

    class _FakePyttsx3TTS:
        def __init__(self, *args, **kwargs):
            pass

        def speak(self, text):
            pass

        def stop(self):
            pass

    pyttsx_stub.Pyttsx3TTS = _FakePyttsx3TTS
    stubs["assistant.tts.pyttsx3_tts"] = pyttsx_stub

    # --- PySide6 ---
    pyside = types.ModuleType("PySide6")
    pyside.__path__ = []
    stubs["PySide6"] = pyside
    for sub in ("QtCore", "QtGui", "QtWidgets", "QtMultimedia", "QtMultimediaWidgets"):
        stubs[f"PySide6.{sub}"] = _make_qt_module(f"PySide6.{sub}")

    # --- edge_tts ---
    edge_mod = types.ModuleType("edge_tts")

    class _FakeCommunicate:
        def __init__(self, text, voice):
            self.text = text
            self.voice = voice

        async def save(self, path):
            Path(path).write_bytes(b"")

    edge_mod.Communicate = _FakeCommunicate
    stubs["edge_tts"] = edge_mod

    # --- pyttsx3 ---
    pyttsx_mod = types.ModuleType("pyttsx3")

    class _FakeEngine:
        def setProperty(self, *a, **kw): pass
        def getProperty(self, *a, **kw): return []
        def say(self, *a, **kw): pass
        def runAndWait(self): pass

    pyttsx_mod.init = lambda: _FakeEngine()
    stubs["pyttsx3"] = pyttsx_mod

    # --- sounddevice ---
    sd_mod = types.ModuleType("sounddevice")
    sd_mod.query_devices = lambda: []
    sd_mod.query_hostapis = lambda: []
    sd_mod.default = types.SimpleNamespace(device=(0, 0))
    sd_mod.rec = lambda *a, **kw: np.zeros(1, dtype="float32")
    sd_mod.wait = lambda: None
    stubs["sounddevice"] = sd_mod

    # --- faster_whisper ---
    fw_mod = types.ModuleType("faster_whisper")
    fw_mod.WhisperModel = type("WhisperModel", (), {"__init__": lambda *a, **kw: None})
    stubs["faster_whisper"] = fw_mod

    # --- openai ---
    openai_mod = types.ModuleType("openai")

    class _FakeOpenAI:
        def __init__(self, *args, **kwargs):
            pass

    openai_mod.OpenAI = _FakeOpenAI
    stubs["openai"] = openai_mod

    return stubs


# ===========================================================================
# Фикстура: временная установка и гарантированное восстановление sys.modules
# ===========================================================================

@pytest.fixture
def module_stubs():
    saved: dict[str, object] = {}
    for name in _STUBBED_MODULE_NAMES:
        saved[name] = sys.modules.get(name, None)

    saved["config"] = sys.modules.get("config", None)
    saved["main"] = sys.modules.get("main", None)

    stubs = _build_stub_modules()
    for name, mod in stubs.items():
        sys.modules[name] = mod

    sys.modules.pop("config", None)
    sys.modules.pop("main", None)

    try:
        yield stubs
    finally:
        for name, previous in saved.items():
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous

        for name in (
            "assistant.tts.edge_tts",
            "assistant.tts.silero_tts",
            "assistant.tts.pyttsx3_tts",
            "assistant.tts.fallback_tts",
            "assistant.audio",
            "assistant.audio.playback",
            "assistant.audio.device",
            "assistant.audio.recorder",
        ):
            if name in saved and saved[name] is not None:
                sys.modules[name] = saved[name]
            elif name not in saved:
                sys.modules.pop(name, None)


# ===========================================================================
# Fake-зависимости для Core
# ===========================================================================

class FakeSTT:
    def __init__(self):
        self.next_text = ""

    def transcribe(self, audio, sample_rate) -> str:
        return self.next_text


class FakeTTS:
    def __init__(self, *args, **kwargs):
        self.spoken: list[str] = []

    def speak(self, text: str) -> None:
        if text:
            self.spoken.append(text)

    def stop(self) -> None:
        pass


class FakeLLM:
    def __init__(self, *args, **kwargs):
        self.calls = 0
        self.answer = "fake-answer"

    def chat(self, user_message: str, system_prompt: str | None = None) -> str:
        self.calls += 1
        return self.answer

    def name(self) -> str:
        return "fake"


# ===========================================================================
# A. Unit smoke Core (без фабрик main)
# ===========================================================================

def _build_core_smoke():
    from assistant.events import EventBus
    from assistant.core import AssistantCore
    from assistant.wake.keyword_detector import KeywordWakeDetector
    from assistant.intent.echo_intent_parser import EchoIntentParser
    from assistant.response.echo_response import EchoResponseGenerator
    from assistant.actions.base import ActionRegistry, ActionContext
    from assistant.actions.actions_impl import (
        GradeStudentAction, OpenPresentationAction,
        OpenVideoAction, NextSlideAction,
    )
    from assistant.actions.validators import (
        GradeStudentValidator, OpenPresentationValidator,
        OpenVideoValidator, NextSlideValidator,
    )
    from assistant.confirmation import KeywordConfirmationParser

    bus = EventBus()
    stt = FakeSTT()
    tts = FakeTTS()

    reg = ActionRegistry()
    reg.register(GradeStudentAction(), GradeStudentValidator())
    reg.register(OpenPresentationAction(), OpenPresentationValidator())
    reg.register(OpenVideoAction(), OpenVideoValidator())
    reg.register(NextSlideAction(), NextSlideValidator())

    ctx = ActionContext(
        addressed_to_assistant=False,
        current_subject=None,
        current_lesson=None,
        gradebook=None,
        gradebook_path=None,
        known_students=[],
        dry_run=True,
    )

    core = AssistantCore(
        stt=stt,
        wake=KeywordWakeDetector(),
        intent_parser=EchoIntentParser(),
        response_gen=EchoResponseGenerator(),
        actions=reg,
        tts=tts,
        confirmation_parser=KeywordConfirmationParser(),
        context=ctx,
    )
    return core, bus, stt, tts


def test_a_core_assembled_with_fake_deps():
    core, bus, stt, tts = _build_core_smoke()
    stt.next_text = "Ассистент, привет"
    r = core.handle_audio(np.zeros(16000, dtype="float32"), 16000)
    assert r.is_addressed is True
    assert r.final_speech
    assert tts.spoken


def test_a_core_uses_only_interfaces():
    core, *_ = _build_core_smoke()
    assert hasattr(core, "stt")
    assert hasattr(core, "tts")
    assert hasattr(core, "intent_parser")
    assert hasattr(core, "response_gen")
    assert hasattr(core, "actions")
    assert not hasattr(core, "silero")
    assert not hasattr(core, "gemini")
    assert not hasattr(core, "whisper")
    assert not hasattr(core, "openrouter")


def test_a_core_does_not_publish_to_event_bus():
    from assistant.events import EventType
    core, bus, stt, tts = _build_core_smoke()
    seen = []
    bus.subscribe(EventType.USER_MESSAGE, lambda e: seen.append(e))
    bus.subscribe(EventType.ASSISTANT_MESSAGE, lambda e: seen.append(e))
    stt.next_text = "Ассистент, привет"
    core.handle_audio(np.zeros(16000, dtype="float32"), 16000)
    assert seen == []


# ===========================================================================
# B. Factory integration — реальные фабрики main.py
# ===========================================================================

def test_b_build_llm_echo_when_provider_echo(module_stubs, monkeypatch):
    import importlib
    main_module = importlib.import_module("main")
    monkeypatch.setattr(main_module.Config, "LLM_PROVIDER", "echo")
    llm = main_module.build_llm()
    assert llm.__class__.__name__ == "EchoLLM"


def test_b_build_llm_router_with_fake_providers(module_stubs, monkeypatch):
    import importlib
    main_module = importlib.import_module("main")
    monkeypatch.setattr(main_module.Config, "LLM_PROVIDER", "router")
    monkeypatch.setattr(main_module.Config, "GEMINI_API_KEY", "fake-gemini")
    monkeypatch.setattr(main_module.Config, "OPENROUTER_API_KEY", "fake-openrouter")
    monkeypatch.setattr(main_module.Config, "LLM_ROUTER_COOLDOWN_SEC", 30.0)

    with mock.patch.object(main_module, "GeminiLLM", FakeLLM), \
         mock.patch.object(main_module, "OpenRouterLLM", FakeLLM):
        llm = main_module.build_llm()

    assert llm.__class__.__name__ == "LLMRouter"


def test_b_build_parsers_router_returns_intent_router(module_stubs, monkeypatch):
    """
    Новый контракт build_parsers при LLM_PROVIDER=router.

    В нормальных условиях (датасет data/intent_examples.json присутствует,
    embedding-провайдер доступен) build_parsers ДОЛЖЕН вернуть IntentRouter,
    а не LLMIntentParser.

    Ослабление до `in ("IntentRouter", "LLMIntentParser")` скрывало бы
    регрессию, при которой каскад случайно перестал собираться.
    Для fallback-пути есть отдельный тест.
    """
    import importlib
    main_module = importlib.import_module("main")
    monkeypatch.setattr(main_module.Config, "LLM_PROVIDER", "router")
    monkeypatch.setattr(main_module.Config, "GEMINI_API_KEY", "fake-gemini")
    monkeypatch.setattr(main_module.Config, "OPENROUTER_API_KEY", "fake-openrouter")

    with mock.patch.object(main_module, "GeminiLLM", FakeLLM), \
         mock.patch.object(main_module, "OpenRouterLLM", FakeLLM):
        llm = main_module.build_llm()

    ip, rg = main_module.build_parsers(llm)

    assert ip.__class__.__name__ == "IntentRouter", (
        f"build_parsers вернул {ip.__class__.__name__}, "
        f"ожидался IntentRouter (датасет присутствует)."
    )
    assert rg.__class__.__name__ == "LLMResponseGenerator"
    assert rg.llm is llm


def test_b_build_parsers_router_fallback_when_dataset_missing(
    module_stubs, monkeypatch, tmp_path
):
    """
    Fallback-путь: если датасет пуст/недоступен, build_parsers корректно
    откатывается на LLMIntentParser. Проверяется с намеренно пустым
    EVA_INTENT_EXAMPLES.
    """
    import importlib
    main_module = importlib.import_module("main")
    monkeypatch.setattr(main_module.Config, "LLM_PROVIDER", "router")
    monkeypatch.setattr(main_module.Config, "GEMINI_API_KEY", "fake-gemini")
    monkeypatch.setattr(main_module.Config, "OPENROUTER_API_KEY", "fake-openrouter")

    # Указываем несуществующий путь — load_intent_examples вернёт {}.
    fake_examples_path = tmp_path / "no_examples.json"
    monkeypatch.setenv("EVA_INTENT_EXAMPLES", str(fake_examples_path))

    # Сбросить кэш датасета, чтобы он перечитал env.
    from assistant.intent.router import dataset as dataset_mod
    dataset_mod.clear_cache()

    with mock.patch.object(main_module, "GeminiLLM", FakeLLM), \
         mock.patch.object(main_module, "OpenRouterLLM", FakeLLM):
        llm = main_module.build_llm()

    ip, rg = main_module.build_parsers(llm)

    # При пустом датасете build_intent_router вернёт None →
    # build_parsers откатится на LLMIntentParser.
    assert ip.__class__.__name__ == "LLMIntentParser", (
        f"Ожидался fallback на LLMIntentParser, получен {ip.__class__.__name__}"
    )
    assert rg.__class__.__name__ == "LLMResponseGenerator"


def test_b_build_parsers_echo_provider(module_stubs, monkeypatch):
    import importlib
    main_module = importlib.import_module("main")
    monkeypatch.setattr(main_module.Config, "LLM_PROVIDER", "echo")
    from assistant.llm.echo_llm import EchoLLM
    ip, rg = main_module.build_parsers(EchoLLM())
    assert ip.__class__.__name__ == "EchoIntentParser"
    assert rg.__class__.__name__ == "EchoResponseGenerator"


def test_b_build_tts_silero(module_stubs, monkeypatch):
    import importlib
    main_module = importlib.import_module("main")
    monkeypatch.setattr(main_module.Config, "TTS_PROVIDER", "silero")
    with mock.patch.object(main_module, "SileroTTS", FakeTTS):
        tts = main_module.build_tts()
    assert isinstance(tts, FakeTTS)


def test_b_build_tts_edge_uses_fallback(module_stubs, monkeypatch):
    import importlib
    main_module = importlib.import_module("main")
    monkeypatch.setattr(main_module.Config, "TTS_PROVIDER", "edge")
    with mock.patch.object(main_module, "EdgeTTS", FakeTTS), \
         mock.patch.object(main_module, "SileroTTS", FakeTTS):
        tts = main_module.build_tts()
    assert tts.__class__.__name__ == "FallbackTTS"
    assert isinstance(tts._primary, FakeTTS)
    assert isinstance(tts._fallback, FakeTTS)


def test_b_build_tts_pyttsx3(module_stubs, monkeypatch):
    import importlib
    main_module = importlib.import_module("main")
    monkeypatch.setattr(main_module.Config, "TTS_PROVIDER", "pyttsx3")
    with mock.patch.object(main_module, "Pyttsx3TTS", FakeTTS):
        tts = main_module.build_tts()
    assert isinstance(tts, FakeTTS)


def test_b_build_actions_registry(module_stubs, monkeypatch):
    import importlib
    main_module = importlib.import_module("main")
    reg = main_module.build_actions()
    assert reg.get("grade_student") is not None
    assert reg.get("open_presentation") is not None
    assert reg.get("open_video") is not None
    assert reg.get("next_slide") is not None


def test_b_build_context_path_from_config(module_stubs, monkeypatch, tmp_path):
    import importlib
    main_module = importlib.import_module("main")
    fake_path = tmp_path / "no_such_journal.xlsx"
    monkeypatch.setattr(main_module.Config, "GRADEBOOK_PATH", str(fake_path))
    ctx = main_module.build_context()
    assert ctx.gradebook_path == str(fake_path)
    assert ctx.gradebook is None
    assert ctx.dry_run is False


# ===========================================================================
# C. Статические проверки
# ===========================================================================

def test_c_application_does_not_rebuild_core():
    path = Path("assistant/ui/app.py")
    assert path.exists(), f"missing: {path}"
    text = path.read_text(encoding="utf-8")

    forbidden = [
        "WhisperSTT(", "SileroTTS(", "GeminiLLM(", "OpenRouterLLM(",
        "LLMRouter(", "build_llm(", "build_tts(",
    ]
    for token in forbidden:
        assert token not in text, f"assistant/ui/app.py содержит '{token}'"


def test_c_no_playwright_in_production_modules():
    forbidden = (
        "playwright",
        "deepseek_browser",
        "deepseek_web_llm",
    )

    root = Path("assistant")
    assert root.is_dir(), "папка assistant не найдена"

    checked = 0
    for path in root.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue

        text = path.read_text(encoding="utf-8", errors="replace").lower()
        for bad in forbidden:
            assert bad not in text, (
                f"{path} содержит запрещённую зависимость '{bad}'"
            )
        checked += 1

    assert checked > 0, "не найдено ни одного production-файла"


# ===========================================================================
# D. Router persistence
# ===========================================================================

def test_d_router_state_class_has_no_persistence_api():
    import inspect
    from assistant.llm.router.router import LLMRouter, _Entry
    from assistant.llm.router.state import ProviderRuntimeState

    router_sig = inspect.signature(LLMRouter.__init__)
    assert "storage" not in router_sig.parameters
    assert "state_file" not in router_sig.parameters
    assert "persist" not in router_sig.parameters

    state_sig = inspect.signature(ProviderRuntimeState.__init__)
    assert "storage" not in state_sig.parameters
    assert "state_file" not in state_sig.parameters
    assert "persist" not in state_sig.parameters

    entry_sig = inspect.signature(_Entry.__init__)
    assert "storage" not in entry_sig.parameters
    assert "state_file" not in entry_sig.parameters
    assert "persist" not in entry_sig.parameters


def test_d_router_state_change_does_not_write_files(tmp_path, monkeypatch):
    from assistant.llm.router import (
        LLMRouter, LLMProviderConfig, NetworkChecker,
    )
    from assistant.llm.router.router import _Entry
    from assistant.llm.router.state import FailureReason, ProviderStatus

    class FakeProvider(FakeLLM):
        pass

    cfg = LLMProviderConfig(
        name="gemini", model="fake", priority=1,
        requires_internet=True, supports_intent=True,
        supports_response=True, supports_json=True,
        timeout=5.0, max_retries=0,
    )
    entry = _Entry(provider=FakeProvider(), config=cfg)
    router = LLMRouter([entry], NetworkChecker())

    before = sorted(p for p in tmp_path.iterdir())
    entry.state.disable(FailureReason.QUOTA_EXHAUSTED)
    assert entry.state.status == ProviderStatus.DISABLED
    after = sorted(p for p in tmp_path.iterdir())
    assert before == after


# ===========================================================================
# Прямой запуск
# ===========================================================================

def _run_all():
    tests = [
        test_a_core_assembled_with_fake_deps,
        test_a_core_uses_only_interfaces,
        test_a_core_does_not_publish_to_event_bus,
        test_c_application_does_not_rebuild_core,
        test_c_no_playwright_in_production_modules,
        test_d_router_state_class_has_no_persistence_api,
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
    print(f"=== {len(tests) - failed}/{len(tests)} INTEGRATION TESTS PASSED (direct) ===", flush=True)
    return failed


def main():
    if not os.path.exists("assistant"):
        print("Запускать из корня проекта.", flush=True)
        sys.exit(2)
    sys.exit(1 if _run_all() else 0)


if __name__ == "__main__":
    main()
