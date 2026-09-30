"""
Тесты состояний Hero-видео (production через IntroView) и AvatarView.

Покрывают:
  - registry: production state_map для SPEAKING/THINKING;
  - IntroView._target_layer_key() — production mapping;
  - AvatarView: безопасное переключение, отсутствие целевого файла
    не трогает текущий renderer;
  - IntroView: set_state не прерывает preview, а применяет состояние
    после окончания (через async-подтверждение _verify_pending_layer);
  - IntroView: старый слой не останавливается до подтверждения нового;
  - IntroView: wait → ok переключает, бесконечный wait абортится.

Тесты используют _FakeLayer вместо реального _MediaLayer для
контроля порядка вызовов. Регистрация fake-слоёв идёт и в
view._layers, и через monkeypatch view._get_layer — иначе
_verify_pending_layer не найдёт слой.

Запуск в offscreen-режиме.
"""
import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from assistant.ui.avatar.base import AvatarRenderer
from assistant.ui.avatar.registry import AvatarRegistry
from assistant.ui.avatar_view import AvatarView
from assistant.ui.state_manager import AssistantState


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


class FakeRenderer(AvatarRenderer):
    instances: list["FakeRenderer"] = []
    fail_on_start: bool = False

    def __init__(self, file_path: Path):
        super().__init__(file_path)
        self.started = False
        self.stopped = False
        self.disposed = False
        self._widget = None
        FakeRenderer.instances.append(self)

    def widget(self):
        from PySide6.QtWidgets import QWidget
        if self._widget is None:
            self._widget = QWidget()
        return self._widget

    def start(self):
        if FakeRenderer.fail_on_start:
            raise RuntimeError("simulated start failure")
        self.started = True

    def stop(self):
        self.stopped = True

    def dispose(self):
        self.disposed = True


@pytest.fixture(autouse=True)
def reset_fakes():
    FakeRenderer.instances.clear()
    FakeRenderer.fail_on_start = False
    yield
    FakeRenderer.instances.clear()
    FakeRenderer.fail_on_start = False


def _make_registry(tmp_path, *, warp=True, speaks=False, thinks=False):
    if warp:
        (tmp_path / "warp.mp4").write_bytes(b"warp")
    if speaks:
        (tmp_path / "speaks.mp4").write_bytes(b"speaks")
    if thinks:
        (tmp_path / "thinks.mp4").write_bytes(b"thinks")
    return AvatarRegistry(
        base_dir=tmp_path,
        state_map={
            AssistantState.SPEAKING.value: "speaks.mp4",
            AssistantState.THINKING.value: "thinks.mp4",
        },
        base_filename="warp.mp4",
    )


@pytest.fixture
def patched_build(monkeypatch):
    import assistant.ui.avatar_view as av
    def _build(path):
        return FakeRenderer(path)
    monkeypatch.setattr(av, "build_renderer_for", _build)


# ===========================================================================
# 1. Registry: production state_map
# ===========================================================================

@pytest.mark.parametrize("state_value,expected_name", [
    (AssistantState.IDLE.value, "warp.mp4"),
    (AssistantState.LISTENING.value, "warp.mp4"),
    (AssistantState.WAITING_CONFIRMATION.value, "warp.mp4"),
    (AssistantState.ERROR.value, "warp.mp4"),
    (AssistantState.SPEAKING.value, "speaks.mp4"),
    (AssistantState.THINKING.value, "thinks.mp4"),
])
def test_registry_production_map(tmp_path, state_value, expected_name):
    reg = _make_registry(tmp_path, warp=True, speaks=True, thinks=True)
    p = reg.file_for_state(state_value)
    assert p is not None
    assert p.name == expected_name


def test_registry_speaking_without_speaks_returns_none(tmp_path):
    reg = _make_registry(tmp_path, warp=True, speaks=False, thinks=True)
    assert reg.file_for_state(AssistantState.SPEAKING.value) is None
    assert reg.file_for_state(AssistantState.IDLE.value).name == "warp.mp4"


def test_registry_thinking_without_thinks_returns_none(tmp_path):
    reg = _make_registry(tmp_path, warp=True, speaks=True, thinks=False)
    assert reg.file_for_state(AssistantState.THINKING.value) is None
    assert reg.file_for_state(AssistantState.IDLE.value).name == "warp.mp4"


# ===========================================================================
# 2. IntroView._target_layer_key — production mapping
# ===========================================================================

@pytest.fixture
def intro_view_factory(qapp, tmp_path, monkeypatch):
    """
    Фабрика IntroView, изолированная по путям. Не запускает плееры
    (autostart=False) — тестируется только логика состояний.
    """
    import assistant.paths as paths_mod

    def _make(*, preview=False, warp=False, speaks=False, thinks=False):
        if preview:
            (tmp_path / "preview.mp4").write_bytes(b"p")
        if warp:
            (tmp_path / "warp.mp4").write_bytes(b"w")
        if speaks:
            (tmp_path / "speaks.mp4").write_bytes(b"s")
        if thinks:
            (tmp_path / "thinks.mp4").write_bytes(b"t")

        monkeypatch.setattr(paths_mod, "preview_video_path",
                            lambda: tmp_path / "preview.mp4")
        monkeypatch.setattr(paths_mod, "warp_video_path",
                            lambda: tmp_path / "warp.mp4")
        monkeypatch.setattr(paths_mod, "speaks_video_path",
                            lambda: tmp_path / "speaks.mp4")
        monkeypatch.setattr(paths_mod, "thinks_video_path",
                            lambda: tmp_path / "thinks.mp4")

        from assistant.ui.intro_view import IntroView
        view = IntroView(autostart=False)
        return view

    return _make


@pytest.mark.parametrize("state,expected", [
    (AssistantState.IDLE, "warp"),
    (AssistantState.LISTENING, "warp"),
    (AssistantState.WAITING_CONFIRMATION, "warp"),
    (AssistantState.ERROR, "warp"),
    (AssistantState.SPEAKING, "speaks"),
    (AssistantState.THINKING, "thinks"),
])
def test_intro_target_layer_key(intro_view_factory, state, expected):
    view = intro_view_factory()
    view.set_state(state)
    assert view._target_layer_key() == expected
    view.deleteLater()


# ===========================================================================
# 3. _FakeLayer — контроль порядка вызовов
# ===========================================================================

class _FakeLayer:
    """
    Fake _MediaLayer для проверки порядка вызовов.
    """
    def __init__(self, key: str, play_result: bool = True,
                 check_result: str = "ok"):
        self.key = key
        self.play_result = play_result
        self.check_result = check_result
        self.pause_calls = 0
        self.play_calls = 0
        self.check_calls = 0
        from PySide6.QtWidgets import QWidget
        self.container = QWidget()

    @property
    def is_ready(self) -> bool:
        return True

    def start_play(self) -> bool:
        self.play_calls += 1
        return self.play_result

    def check_after_play(self) -> str:
        self.check_calls += 1
        return self.check_result

    def pause(self) -> None:
        self.pause_calls += 1

    def stop(self) -> None:
        pass

    def sync_view(self) -> None:
        pass


def _install_fake_layers(view, monkeypatch, layers: dict):
    """
    Регистрирует fake-слои и в view._layers, и через monkeypatch
    view._get_layer. Иначе _verify_pending_layer не найдёт слой
    в view._layers.get(pending_key).
    """
    view._layers.update(layers)
    monkeypatch.setattr(view, "_get_layer", lambda key: layers.get(key))
    monkeypatch.setattr(view._stack, "setCurrentWidget",
                        lambda *_a, **_k: None)


# ===========================================================================
# 4. preview не прерывается, состояние применяется после EndOfMedia
# ===========================================================================

def test_intro_preview_not_interrupted_by_state(
    qapp, intro_view_factory, monkeypatch
):
    """
    preview → SPEAKING: preview не прерывается, после EndOfMedia
    переключаемся на speaks через async-подтверждение.

    Используются fake-слои, чтобы контролировать check_after_play.
    """
    view = intro_view_factory(preview=True, warp=True, speaks=True)

    preview = _FakeLayer("preview")
    speaks = _FakeLayer("speaks", play_result=True, check_result="ok")
    warp = _FakeLayer("warp")

    layers = {"preview": preview, "speaks": speaks, "warp": warp}
    _install_fake_layers(view, monkeypatch, layers)

    view._preview_playing = True
    view._visible_layer_key = "preview"

    # SPEAKING во время preview — состояние запоминается.
    view.set_state(AssistantState.SPEAKING)
    assert view._visible_layer_key == "preview"
    assert view._current_state == "speaking"

    # Симулируем EndOfMedia.
    view._preview_playing = False
    view._apply_state_to_view()

    # Целевой слой установлен в pending, но visible пока preview.
    assert view._pending_layer_key == "speaks"
    assert view._visible_layer_key == "preview"

    # Подтверждение.
    view._verify_pending_layer()
    assert view._visible_layer_key == "speaks"

    view.deleteLater()


def test_intro_preview_finished_warp_missing_keeps_preview(
    qapp, intro_view_factory
):
    """
    preview закончился, warp/speaks/thinks отсутствуют
    → preview остаётся видимым.
    """
    view = intro_view_factory(preview=True)

    view._preview_playing = True
    view._visible_layer_key = "preview"
    view._preview_playing = False
    view.set_state(AssistantState.IDLE)

    assert view._visible_layer_key == "preview"
    assert view._pending_layer_key is None

    view.deleteLater()


def test_intro_speaking_without_speaks_keeps_current(
    qapp, intro_view_factory
):
    """
    warp видим, speaks.mp4 отсутствует → остаёмся на warp.
    """
    view = intro_view_factory(preview=False, warp=True, speaks=False)
    view._visible_layer_key = "warp"
    view.set_state(AssistantState.SPEAKING)

    assert view._visible_layer_key == "warp"
    assert view._pending_layer_key is None

    view.deleteLater()


# ===========================================================================
# 5. IntroView: НЕ трогать старый слой до подтверждения нового
# ===========================================================================

def test_intro_does_not_pause_old_before_new_confirmed(
    qapp, intro_view_factory, monkeypatch
):
    """
    warp видим, пытаемся переключиться на битый speaks.
    Проверка провалена → visible_layer_key всё ещё warp,
    warp.pause() НЕ вызывался.
    """
    view = intro_view_factory()
    view._visible_layer_key = "warp"

    warp = _FakeLayer("warp")
    speaks = _FakeLayer("speaks", play_result=True, check_result="fail")

    layers = {"warp": warp, "speaks": speaks}
    _install_fake_layers(view, monkeypatch, layers)

    view.set_state(AssistantState.SPEAKING)
    assert speaks.play_calls == 1
    assert view._visible_layer_key == "warp"
    assert warp.pause_calls == 0

    view._verify_pending_layer()
    assert view._visible_layer_key == "warp"
    assert warp.pause_calls == 0
    assert view._pending_layer_key is None

    view.deleteLater()


def test_intro_pauses_old_only_after_confirmed(
    qapp, intro_view_factory, monkeypatch
):
    """
    warp видим, переключаемся на speaks. Проверка ok →
    visible_layer_key = speaks, warp.pause() вызван.
    """
    view = intro_view_factory()
    view._visible_layer_key = "warp"

    warp = _FakeLayer("warp")
    speaks = _FakeLayer("speaks", play_result=True, check_result="ok")

    layers = {"warp": warp, "speaks": speaks}
    _install_fake_layers(view, monkeypatch, layers)

    view.set_state(AssistantState.SPEAKING)
    assert speaks.play_calls == 1
    assert view._visible_layer_key == "warp"
    assert warp.pause_calls == 0

    view._verify_pending_layer()
    assert view._visible_layer_key == "speaks"
    assert warp.pause_calls == 1

    view.deleteLater()


def test_intro_start_play_failed_does_not_change_anything(
    qapp, intro_view_factory, monkeypatch
):
    """
    start_play вернул False → old не трогается, pending не ставится.
    """
    view = intro_view_factory()
    view._visible_layer_key = "warp"

    warp = _FakeLayer("warp")
    speaks = _FakeLayer("speaks", play_result=False, check_result="ok")

    layers = {"warp": warp, "speaks": speaks}
    _install_fake_layers(view, monkeypatch, layers)

    view.set_state(AssistantState.SPEAKING)
    assert speaks.play_calls == 1
    assert view._visible_layer_key == "warp"
    assert warp.pause_calls == 0
    assert view._pending_layer_key is None

    view.deleteLater()


def test_intro_wait_then_ok_switches(
    qapp, intro_view_factory, monkeypatch
):
    """
    Первый check — wait, второй — ok. Переключение после второго.
    """
    view = intro_view_factory()
    view._visible_layer_key = "warp"

    warp = _FakeLayer("warp")

    class _WaitThenOkLayer(_FakeLayer):
        def __init__(self, key):
            super().__init__(key)
            self._n = 0

        def check_after_play(self):
            self.check_calls += 1
            self._n += 1
            return "wait" if self._n == 1 else "ok"

    speaks = _WaitThenOkLayer("speaks")

    layers = {"warp": warp, "speaks": speaks}
    _install_fake_layers(view, monkeypatch, layers)

    view.set_state(AssistantState.SPEAKING)
    assert view._pending_layer_key == "speaks"

    # Первый check — wait.
    view._verify_pending_layer()
    assert view._pending_layer_key == "speaks"
    assert view._visible_layer_key == "warp"
    assert warp.pause_calls == 0

    # Второй — ok.
    view._verify_pending_layer()
    assert view._pending_layer_key is None
    assert view._visible_layer_key == "speaks"
    assert warp.pause_calls == 1

    view.deleteLater()


def test_intro_max_wait_aborts(
    qapp, intro_view_factory, monkeypatch
):
    """
    Бесконечный wait → после MAX_WAIT_MS переключение отменяется,
    старый слой не тронут.
    """
    import assistant.ui.intro_view as intro_mod

    view = intro_view_factory()
    view._visible_layer_key = "warp"

    warp = _FakeLayer("warp")
    speaks = _FakeLayer("speaks", play_result=True, check_result="wait")

    layers = {"warp": warp, "speaks": speaks}
    _install_fake_layers(view, monkeypatch, layers)

    view.set_state(AssistantState.SPEAKING)
    assert view._pending_layer_key == "speaks"

    # Эмулируем исчерпание окна ожидания.
    view._pending_waited_ms = intro_mod.MAX_WAIT_MS
    view._verify_pending_layer()

    assert view._pending_layer_key is None
    assert view._visible_layer_key == "warp"
    assert warp.pause_calls == 0

    view.deleteLater()


# ===========================================================================
# 6. AvatarView: безопасное переключение
# ===========================================================================

def test_avatar_warp_for_idle(qapp, tmp_path, patched_build):
    registry = _make_registry(tmp_path, warp=True)
    view = AvatarView(registry=registry)
    view.set_state(AssistantState.IDLE)
    assert view._current_renderer is not None
    assert view._current_renderer.file_path.name == "warp.mp4"
    view.deleteLater()


def test_avatar_speaking_uses_speaks(qapp, tmp_path, patched_build):
    registry = _make_registry(tmp_path, warp=True, speaks=True)
    view = AvatarView(registry=registry)
    view.set_state(AssistantState.IDLE)
    view.set_state(AssistantState.SPEAKING)
    assert view._current_renderer.file_path.name == "speaks.mp4"
    view.deleteLater()


def test_avatar_thinking_uses_thinks(qapp, tmp_path, patched_build):
    registry = _make_registry(tmp_path, warp=True, thinks=True)
    view = AvatarView(registry=registry)
    view.set_state(AssistantState.IDLE)
    view.set_state(AssistantState.THINKING)
    assert view._current_renderer.file_path.name == "thinks.mp4"
    view.deleteLater()


def test_avatar_speaking_without_speaks_keeps_warp(
    qapp, tmp_path, patched_build
):
    registry = _make_registry(tmp_path, warp=True, speaks=False)
    view = AvatarView(registry=registry)
    view.set_state(AssistantState.IDLE)
    renderer_before = view._current_renderer

    view.set_state(AssistantState.SPEAKING)
    assert view._current_renderer is renderer_before
    view.deleteLater()


def test_avatar_thinking_without_thinks_keeps_warp(
    qapp, tmp_path, patched_build
):
    registry = _make_registry(tmp_path, warp=True, thinks=False)
    view = AvatarView(registry=registry)
    view.set_state(AssistantState.IDLE)
    renderer_before = view._current_renderer

    view.set_state(AssistantState.THINKING)
    assert view._current_renderer is renderer_before
    view.deleteLater()


def test_avatar_switch_failure_keeps_old(qapp, tmp_path, patched_build):
    registry = _make_registry(tmp_path, warp=True, speaks=True)
    view = AvatarView(registry=registry)
    view.set_state(AssistantState.IDLE)
    old = view._current_renderer
    assert old.file_path.name == "warp.mp4"

    FakeRenderer.fail_on_start = True
    view.set_state(AssistantState.SPEAKING)

    assert view._current_renderer is old
    assert view._current_renderer.file_path.name == "warp.mp4"
    view.deleteLater()


def test_avatar_missing_warp_does_not_destroy_current(
    qapp, tmp_path, patched_build
):
    registry = _make_registry(tmp_path, warp=True, speaks=True)
    view = AvatarView(registry=registry)
    view.set_state(AssistantState.SPEAKING)
    renderer_before = view._current_renderer

    (tmp_path / "warp.mp4").unlink()
    view.set_state(AssistantState.IDLE)
    assert view._current_renderer is renderer_before
    view.deleteLater()


def run_all():
    print("pytest -v tools/test_avatar_video_states.py", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(run_all())
