"""
Тесты слоя TTS.

  - TTSEngine (base) — абстрактность;
  - Pyttsx3TTS — с замоканным pyttsx3 (без реального импорта);
  - EdgeTTS — с замоканными edge_tts и assistant.audio.playback;
  - SileroTTS — с одним общим fake torch на процесс (без повторного импорта);
  - FallbackTTS — чистая логика выбора провайдера.

Запуск через pytest:
    pytest -v tools/test_tts.py
Прямой запуск:
    python -m tools.test_tts

Никакого реального звука, интернета, Silero-модели, pyttsx3, GUI.
Не требует установки sounddevice, pyttsx3, edge_tts, torch.

ВАЖНО: фейковые модули assistant.audio/playback/sounddevice ставятся
на время тестов через autouse-фикстуру и восстанавливаются в teardown.
На уровне модуля sys.modules НЕ мутируется — иначе следующие тесты
(например, test_runtime_apply) получат пустой assistant.audio.
"""
import importlib
import os
import sys
import types
from unittest import mock

import pytest

from assistant.tts.base import TTSEngine
from assistant.tts.fallback_tts import FallbackTTS


# ===========================================================================
# Фикстура: фейковые модули assistant.audio / sounddevice
# ===========================================================================

_FAKE_MODULE_NAMES = (
    "assistant.audio",
    "assistant.audio.playback",
    "sounddevice",
)


@pytest.fixture(autouse=True, scope="module")
def fake_audio_modules():
    """
    Изолированно подменяет assistant.audio / assistant.audio.playback /
    sounddevice на время этого тестового модуля. В teardown
    восстанавливает sys.modules как было.
    """
    saved = {name: sys.modules.get(name, None) for name in _FAKE_MODULE_NAMES}

    audio_pkg = types.ModuleType("assistant.audio")
    audio_pkg.__path__ = []

    playback = types.ModuleType("assistant.audio.playback")

    def _noop_play_wav(path):
        playback.last_play_wav = path

    def _noop_play_mp3(path):
        playback.last_play_mp3 = path

    playback.play_wav = _noop_play_wav
    playback.play_mp3 = _noop_play_mp3
    playback.last_play_wav = None
    playback.last_play_mp3 = None

    audio_pkg.playback = playback

    sys.modules["assistant.audio"] = audio_pkg
    sys.modules["assistant.audio.playback"] = playback
    sys.modules.setdefault("sounddevice", types.ModuleType("sounddevice"))

    # Сбрасываем кэш assistant.tts.*, чтобы они перечитали подменённые модули.
    for mod_name in (
        "assistant.tts.edge_tts",
        "assistant.tts.silero_tts",
        "assistant.tts.pyttsx3_tts",
    ):
        sys.modules.pop(mod_name, None)

    try:
        yield {
            "audio": audio_pkg,
            "playback": playback,
        }
    finally:
        for name, previous in saved.items():
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous

        # Сбрасываем кэш, чтобы следующие тесты импортировали
        # реальные модули assistant.tts.*
        for mod_name in (
            "assistant.tts.edge_tts",
            "assistant.tts.silero_tts",
            "assistant.tts.pyttsx3_tts",
        ):
            sys.modules.pop(mod_name, None)


# ===========================================================================
# Fake TTS для проверки fallback-логики
# ===========================================================================

class FakeTTS(TTSEngine):
    def __init__(self, name: str, behavior: str = "ok"):
        self.name_ = name
        self.behavior = behavior
        self.spoken: list[str] = []
        self.stop_called = 0

    def speak(self, text: str) -> None:
        if self.behavior == "raise":
            raise RuntimeError(f"{self.name_} failed")
        self.spoken.append(text)

    def stop(self) -> None:
        self.stop_called += 1


# ===========================================================================
# Base
# ===========================================================================

def test_tts_engine_is_abstract():
    try:
        TTSEngine()  # type: ignore[abstract]
        assert False, "TTSEngine() не должен создаваться напрямую"
    except TypeError:
        pass


def test_tts_engine_requires_speak_not_stop():
    class OnlySpeak(TTSEngine):
        def speak(self, text: str) -> None:
            pass

    OnlySpeak()


def test_fake_tts_is_tts_engine():
    assert isinstance(FakeTTS("a"), TTSEngine)


# ===========================================================================
# Pyttsx3TTS — без реального pyttsx3
# ===========================================================================

class _FakePyttsx3Engine:
    def __init__(self, voices=None):
        self.props: dict = {}
        self.said: list[str] = []
        self.run_and_wait = 0
        self._voices = voices or []

    def setProperty(self, name, value):
        self.props[name] = value

    def getProperty(self, name):
        if name == "voices":
            return self._voices
        return self.props.get(name)

    def say(self, text):
        self.said.append(text)

    def runAndWait(self):
        self.run_and_wait += 1


def _load_pyttsx3_tts_with_fake_engine(fake_engine):
    fake_mod = types.ModuleType("pyttsx3")
    fake_mod.init = lambda: fake_engine

    sys.modules.pop("assistant.tts.pyttsx3_tts", None)

    with mock.patch.dict(sys.modules, {"pyttsx3": fake_mod}):
        mod = importlib.import_module("assistant.tts.pyttsx3_tts")
    return mod


def test_pyttsx3_tts_say_and_run_and_wait():
    fake_engine = _FakePyttsx3Engine()
    mod = _load_pyttsx3_tts_with_fake_engine(fake_engine)

    tts = mod.Pyttsx3TTS()
    tts.speak("привет")

    assert fake_engine.said == ["привет"]
    assert fake_engine.run_and_wait == 1
    assert fake_engine.props.get("rate") == 180


def test_pyttsx3_tts_skips_empty_text():
    fake_engine = _FakePyttsx3Engine()
    mod = _load_pyttsx3_tts_with_fake_engine(fake_engine)

    tts = mod.Pyttsx3TTS()
    tts.speak("")
    assert fake_engine.said == []
    assert fake_engine.run_and_wait == 0


def test_pyttsx3_tts_voice_hint_matches_id():
    v1 = types.SimpleNamespace(name="English", id="en-us")
    v2 = types.SimpleNamespace(name="Irina", id="ru-irina")
    fake_engine = _FakePyttsx3Engine(voices=[v1, v2])
    mod = _load_pyttsx3_tts_with_fake_engine(fake_engine)

    tts = mod.Pyttsx3TTS(voice_hint="irina")
    assert fake_engine.props.get("voice") == "ru-irina"


def test_pyttsx3_tts_no_voice_hint_match_keeps_default():
    v1 = types.SimpleNamespace(name="English", id="en-us")
    fake_engine = _FakePyttsx3Engine(voices=[v1])
    mod = _load_pyttsx3_tts_with_fake_engine(fake_engine)

    tts = mod.Pyttsx3TTS(voice_hint="nonexistent")
    assert "voice" not in fake_engine.props


# ===========================================================================
# EdgeTTS — без edge_tts и без sounddevice
# ===========================================================================

def _load_edge_tts_module():
    sys.modules.pop("assistant.tts.edge_tts", None)
    return importlib.import_module("assistant.tts.edge_tts")


def test_edge_tts_success_plays_and_cleans_up(tmp_path, fake_audio_modules):
    saved_paths: list[str] = []

    class FakeCommunicate:
        def __init__(self, text, voice):
            self.text = text
            self.voice = voice

        async def save(self, path):
            saved_paths.append(path)
            with open(path, "wb") as f:
                f.write(b"ID3")

    fake_edge = types.ModuleType("edge_tts")
    fake_edge.Communicate = FakeCommunicate

    with mock.patch.dict(sys.modules, {"edge_tts": fake_edge}), \
         mock.patch("assistant.paths.temp_dir", return_value=tmp_path):
        mod = _load_edge_tts_module()
        playback = fake_audio_modules["playback"]
        playback.last_play_mp3 = None

        tts = mod.EdgeTTS(voice="ru-RU-SvetlanaNeural")
        tts.speak("привет")

        assert playback.last_play_mp3 is not None
        assert playback.last_play_mp3.endswith(".mp3")
        assert saved_paths and saved_paths[0].endswith(".mp3")
        assert not os.path.exists(saved_paths[0])


def test_edge_tts_skips_empty_text(fake_audio_modules):
    fake_edge = types.ModuleType("edge_tts")

    class FakeCommunicate:
        def __init__(self, text, voice):
            raise AssertionError("Communicate не должен создаваться для пустого текста")

    fake_edge.Communicate = FakeCommunicate

    with mock.patch.dict(sys.modules, {"edge_tts": fake_edge}):
        mod = _load_edge_tts_module()
        playback = fake_audio_modules["playback"]
        playback.last_play_mp3 = None

        tts = mod.EdgeTTS()
        tts.speak("")
        assert playback.last_play_mp3 is None


def test_edge_tts_propagates_network_error(tmp_path, fake_audio_modules):
    class FakeCommunicate:
        def __init__(self, text, voice):
            pass

        async def save(self, path):
            raise ConnectionError("Cannot connect to host speech.platform.bing.com:443")

    fake_edge = types.ModuleType("edge_tts")
    fake_edge.Communicate = FakeCommunicate

    with mock.patch.dict(sys.modules, {"edge_tts": fake_edge}), \
         mock.patch("assistant.paths.temp_dir", return_value=tmp_path):
        mod = _load_edge_tts_module()

        tts = mod.EdgeTTS()
        raised = False
        try:
            tts.speak("привет")
        except ConnectionError:
            raised = True
        assert raised is True


# ===========================================================================
# SileroTTS — ОДИН импорт на процесс, без reload и без повторного import.
# Fake torch и FakeModel создаются один раз; behavior переключается из тестов.
# ===========================================================================

class _SharedFakeModel:
    def __init__(self):
        self.behavior = "ok"
        self.to_calls = 0
        self.apply_calls: list[dict] = []

    def reset(self, behavior: str = "ok"):
        self.behavior = behavior
        self.to_calls = 0
        self.apply_calls = []

    def to(self, device):
        self.to_calls += 1
        return self

    def apply_tts(self, text, speaker, sample_rate):
        self.apply_calls.append({
            "text": text, "speaker": speaker, "sample_rate": sample_rate,
        })
        if self.behavior == "raise":
            raise RuntimeError("apply_tts failed")
        import numpy as np
        return mock.MagicMock(numpy=lambda: np.zeros(1000, dtype="float32"))


_SHARED_MODEL = _SharedFakeModel()


class _SharedFakeImporter:
    def __init__(self, path):
        self.path = path

    def load_pickle(self, group, name):
        return _SHARED_MODEL


_FAKE_TORCH = types.ModuleType("torch")
_FAKE_TORCH.package = types.SimpleNamespace(
    PackageImporter=_SharedFakeImporter
)
_FAKE_TORCH.set_num_threads = lambda n: None
_FAKE_TORCH.device = lambda name: name


@pytest.fixture(autouse=True, scope="module")
def fake_torch_module():
    saved = sys.modules.get("torch", None)
    sys.modules["torch"] = _FAKE_TORCH
    sys.modules.pop("assistant.tts.silero_tts", None)
    try:
        yield
    finally:
        if saved is None:
            sys.modules.pop("torch", None)
        else:
            sys.modules["torch"] = saved
        sys.modules.pop("assistant.tts.silero_tts", None)


def _load_silero():
    sys.modules.pop("assistant.tts.silero_tts", None)
    return importlib.import_module("assistant.tts.silero_tts")


def test_silero_tts_missing_model_raises(tmp_path, fake_audio_modules):
    _SHARED_MODEL.reset("ok")
    mod = _load_silero()
    fake_path = tmp_path / "does_not_exist.pt"
    playback = fake_audio_modules["playback"]
    playback.last_play_wav = None

    tts = mod.SileroTTS(model_path=str(fake_path))
    raised = False
    try:
        tts.speak("привет")
    except FileNotFoundError:
        raised = True
    assert raised is True
    assert playback.last_play_wav is None


def test_silero_tts_success_calls_apply_and_play(tmp_path, fake_audio_modules):
    _SHARED_MODEL.reset("ok")
    mod = _load_silero()
    model_path = tmp_path / "v4_ru.pt"
    model_path.write_bytes(b"fake")

    playback = fake_audio_modules["playback"]
    playback.last_play_wav = None

    with mock.patch("assistant.paths.temp_dir", return_value=tmp_path):
        tts = mod.SileroTTS(
            speaker="xenia",
            model_path=str(model_path),
            sample_rate=48000,
        )
        tts.speak("привет")

    assert _SHARED_MODEL.apply_calls, "apply_tts не был вызван"
    call = _SHARED_MODEL.apply_calls[0]
    assert call["text"] == "привет"
    assert call["speaker"] == "xenia"
    assert call["sample_rate"] == 48000
    assert playback.last_play_wav is not None


def test_silero_tts_apply_error_propagates(tmp_path, fake_audio_modules):
    _SHARED_MODEL.reset("raise")
    mod = _load_silero()
    model_path = tmp_path / "v4_ru.pt"
    model_path.write_bytes(b"fake")

    playback = fake_audio_modules["playback"]
    playback.last_play_wav = None

    with mock.patch("assistant.paths.temp_dir", return_value=tmp_path):
        tts = mod.SileroTTS(model_path=str(model_path))
        raised = False
        try:
            tts.speak("привет")
        except RuntimeError:
            raised = True
    assert raised is True
    assert playback.last_play_wav is None


# ===========================================================================
# FallbackTTS
# ===========================================================================

def test_fallback_uses_primary_when_ok():
    p = FakeTTS("primary", "ok")
    f = FakeTTS("fallback", "ok")
    tts = FallbackTTS(primary=p, fallback=f)

    tts.speak("привет")

    assert p.spoken == ["привет"]
    assert f.spoken == []
    assert tts.primary_available is True


def test_fallback_uses_fallback_when_primary_fails():
    p = FakeTTS("primary", "raise")
    f = FakeTTS("fallback", "ok")
    tts = FallbackTTS(primary=p, fallback=f)

    tts.speak("привет")

    assert p.spoken == []
    assert f.spoken == ["привет"]
    assert tts.primary_available is False


def test_fallback_does_not_retry_primary_after_first_failure():
    p = FakeTTS("primary", "raise")
    f = FakeTTS("fallback", "ok")
    tts = FallbackTTS(primary=p, fallback=f)

    tts.speak("один")
    tts.speak("два")

    assert p.spoken == []
    assert f.spoken == ["один", "два"]
    assert tts.primary_available is False


def test_fallback_raises_when_both_fail():
    p = FakeTTS("primary", "raise")
    f = FakeTTS("fallback", "raise")
    tts = FallbackTTS(primary=p, fallback=f)

    raised = False
    try:
        tts.speak("привет")
    except RuntimeError:
        raised = True
    assert raised is True
    assert tts.primary_available is False


def test_fallback_skips_empty_text():
    p = FakeTTS("primary", "ok")
    f = FakeTTS("fallback", "ok")
    tts = FallbackTTS(primary=p, fallback=f)

    tts.speak("")
    assert p.spoken == []
    assert f.spoken == []


def test_fallback_stop_calls_both():
    p = FakeTTS("primary", "ok")
    f = FakeTTS("fallback", "ok")
    tts = FallbackTTS(primary=p, fallback=f)

    tts.stop()
    assert p.stop_called == 1
    assert f.stop_called == 1


def test_fallback_stop_does_not_break_on_error():
    class BrokenStop(FakeTTS):
        def stop(self):
            raise RuntimeError("stop failed")

    p = BrokenStop("primary", "ok")
    f = FakeTTS("fallback", "ok")
    tts = FallbackTTS(primary=p, fallback=f)

    tts.stop()
    assert f.stop_called == 1


# ===========================================================================
# Прямой запуск
# ===========================================================================

def _run_all():
    tests = [
        test_tts_engine_is_abstract,
        test_tts_engine_requires_speak_not_stop,
        test_fake_tts_is_tts_engine,
        test_pyttsx3_tts_say_and_run_and_wait,
        test_pyttsx3_tts_skips_empty_text,
        test_pyttsx3_tts_voice_hint_matches_id,
        test_pyttsx3_tts_no_voice_hint_match_keeps_default,
        test_edge_tts_skips_empty_text,
        test_fallback_uses_primary_when_ok,
        test_fallback_uses_fallback_when_primary_fails,
        test_fallback_does_not_retry_primary_after_first_failure,
        test_fallback_raises_when_both_fail,
        test_fallback_skips_empty_text,
        test_fallback_stop_calls_both,
        test_fallback_stop_does_not_break_on_error,
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
    print(f"=== {len(tests) - failed}/{len(tests)} TTS TESTS PASSED (direct) ===", flush=True)
    return failed


def main():
    if not os.path.exists("assistant"):
        print("Запускать из корня проекта.", flush=True)
        sys.exit(2)
    sys.exit(1 if _run_all() else 0)


if __name__ == "__main__":
    main()
