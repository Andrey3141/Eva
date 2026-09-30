"""
Application — связка Core ↔ EventBus ↔ MainWindow ↔ ContinuousListener.

Все обновления IntroView идут через Qt-сигнал state_for_ui.
_on_state_changed может быть вызван из eva-core-worker (через
EventBus), но state_for_ui.emit в этом случае гарантирует queued
delivery в GUI thread. Никакие QWidget/QMediaPlayer не создаются
и не изменяются из worker-потока.
"""
import threading
from typing import Optional

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import QApplication

from ..events import EventBus, Event, EventType
from ..core import AssistantCore
from .main_window import MainWindow
from .state_manager import StateManager, AssistantState

from config import Config

from ..audio import ContinuousListener, describe_device, pick_input_device
from ..audio.device import list_input_devices


_LLM_KEYS = frozenset({
    "LLM_PROVIDER",
    "GEMINI_MODEL",
    "GROQ_MODEL",
    "CEREBRAS_MODEL",
    "OPENROUTER_MODEL",
    "DEEPSEEK_MODEL",
})

_STT_KEYS = frozenset({
    "WHISPER_MODEL",
    "WHISPER_LANGUAGE",
})

_TTS_KEYS = frozenset({
    "TTS_PROVIDER",
    "SILERO_SPEAKER",
    "UI_VOLUME",
    "UI_SPEECH_RATE",
})

_CONTEXT_KEYS = frozenset({
    "PRESENTATIONS_DIR",
    "GRADEBOOK_PATH",
    "PRESENTATION_MATCH_THRESHOLD",
    "PRESENTATION_AMBIGUITY_MARGIN",
    "PARAMETER_ROUTER_MODE",
})

_REBUILDABLE_KEYS = _LLM_KEYS | _STT_KEYS | _TTS_KEYS | _CONTEXT_KEYS


def _device_still_valid(device) -> bool:
    if device is None:
        return False
    try:
        devices = list_input_devices()
    except Exception:
        return False
    for d in devices:
        if d.index == device.index and d.channels > 0:
            return True
    return False


def _device_by_index(index):
    try:
        for d in list_input_devices():
            if d.index == index and d.channels > 0:
                return d
    except Exception:
        return None
    return None


class Application(QObject):
    run_audio_sig = Signal()
    rebuild_finished_sig = Signal(dict)

    # Сигнал, эмитируемый из любого потока. Qt.AutoConnection
    # при доставке из non-GUI потока в GUI-thread объект даёт
    # QueuedConnection: слот _on_state_for_ui выполняется
    # в GUI thread. Это гарантирует, что все вызовы IntroView
    # происходят в GUI thread.
    state_for_ui = Signal(object)

    def __init__(self, core: AssistantCore, bus: EventBus,
                 state_mgr: StateManager, settings_store=None,
                 rebuild_callbacks=None, window=None):
        super().__init__()
        self.core = core
        self.bus = bus
        self.state_mgr = state_mgr
        self._settings_store = settings_store
        self._rebuild_callbacks = dict(rebuild_callbacks or {})
        self._window = window

        self._rebuild_lock = threading.Lock()
        self._rebuilding = False
        self._pending_keys: set[str] = set()
        self._rebuild_thread: Optional[threading.Thread] = None

        # Подписываем сигнал на слот _on_state_for_ui. Оба — в GUI
        # thread, потому что Application создаётся в run_app().
        # При emit из worker-потока Qt автоматически выберет
        # QueuedConnection.
        self.state_for_ui.connect(self._on_state_for_ui)

        preferred_index = None
        if self._settings_store is not None and self._settings_store.has("INPUT_DEVICE_INDEX"):
            preferred_index = self._settings_store.get("INPUT_DEVICE_INDEX")
        elif Config.INPUT_DEVICE_INDEX is not None:
            preferred_index = Config.INPUT_DEVICE_INDEX

        self.input_device = None
        if preferred_index is not None:
            self.input_device = _device_by_index(int(preferred_index))
        if self.input_device is None:
            self.input_device = pick_input_device()

        if self.input_device is not None:
            print(f"[AUDIO] Input: {describe_device(self.input_device)}", flush=True)
        else:
            print("[AUDIO] Не найдено физического устройства ввода.", flush=True)

        self.listener = ContinuousListener(
            sample_rate=Config.SAMPLE_RATE,
            on_segment=self._on_segment,
            device=self.input_device,
            muted=True,
        )
        self.listener.start()

        bus.subscribe(EventType.MICROPHONE_MUTED_CHANGED, self._on_mic_muted)
        bus.subscribe(EventType.ASSISTANT_STATE_CHANGED, self._on_state_changed)
        bus.subscribe(EventType.CONFIG_CHANGED, self._on_config_changed)

    # ------------------------------------------------------------------
    def set_window(self, window) -> None:
        self._window = window

    # ------------------------------------------------------------------
    # GUI-thread slots
    # ------------------------------------------------------------------
    def _on_state_for_ui(self, state) -> None:
        """
        Выполняется в GUI thread. Передаёт состояние в IntroView.

        Диагностический print для подтверждения потока.
        """
        try:
            from PySide6.QtCore import QThread
            app = QApplication.instance()
            gui_thread = app.thread() if app is not None else None
            cur = QThread.currentThread()
            print(
                f"[INTRO] set_state thread={cur} gui={gui_thread}",
                flush=True,
            )
        except Exception:
            pass

        try:
            w = self._window
            if w is None:
                return
            scene = getattr(w, "scene", None)
            if scene is None:
                return
            intro = getattr(scene, "intro", None)
            if intro is None:
                return
            setter = getattr(intro, "set_state", None)
            if setter is None:
                return
            setter(state)
        except Exception as e:
            print(f"[APP] intro.set_state error: {e}", flush=True)

    # ------------------------------------------------------------------
    # Worker-thread callbacks
    # ------------------------------------------------------------------
    def _on_mic_muted(self, event: Event) -> None:
        muted = bool(event.payload.get("muted", True))
        try:
            self.listener.set_muted(muted)
            print(f"[AUDIO] mute={muted} (listening={not muted})", flush=True)
        except Exception as e:
            print(f"[AUDIO] set_muted error: {e}", flush=True)

    def _on_state_changed(self, event: Event) -> None:
        """
        Может быть вызван из eva-core-worker через EventBus.publish.
        Gate-управление безопасно из worker, но UI-часть
        делегируется через state_for_ui.emit — queued в GUI thread.
        """
        state = event.payload.get("state")

        # Gate ContinuousListener — это не Qt-объект, вызов безопасен
        # из worker.
        if state == AssistantState.SPEAKING:
            try:
                self.listener.close_gate()
            except Exception:
                pass
        elif state in (AssistantState.IDLE,
                       AssistantState.WAITING_CONFIRMATION,
                       AssistantState.THINKING,
                       AssistantState.LISTENING,
                       AssistantState.ERROR):
            try:
                self.listener.open_gate()
            except Exception:
                pass

        # UI: только через сигнал, чтобы попасть в GUI thread.
        self.state_for_ui.emit(state)

    # ------------------------------------------------------------------
    def _on_config_changed(self, event: Event) -> None:
        keys = list(event.payload.get("changed_keys") or [])
        if not keys:
            return

        keys_set = set(keys) & _REBUILDABLE_KEYS
        if not keys_set:
            return

        with self._rebuild_lock:
            self._pending_keys |= keys_set
            if self._rebuilding:
                return
            self._rebuilding = True

        self._rebuild_thread = threading.Thread(
            target=self._rebuild_loop,
            daemon=True,
            name="eva-rebuild",
        )
        self._rebuild_thread.start()

    def _rebuild_loop(self) -> None:
        try:
            while True:
                with self._rebuild_lock:
                    if not self._pending_keys:
                        return
                    keys = set(self._pending_keys)
                    self._pending_keys.clear()

                try:
                    self._do_rebuild(list(keys))
                    self.rebuild_finished_sig.emit({"ok": True, "error": ""})
                except Exception as e:
                    print(f"[REBUILD] error: {type(e).__name__}: {e}", flush=True)
                    self.rebuild_finished_sig.emit(
                        {"ok": False, "error": f"{type(e).__name__}: {e}"}
                    )
        finally:
            with self._rebuild_lock:
                self._rebuilding = False
                if self._pending_keys:
                    self._rebuilding = True
                    self._rebuild_thread = threading.Thread(
                        target=self._rebuild_loop,
                        daemon=True,
                        name="eva-rebuild",
                    )
                    self._rebuild_thread.start()

    def _do_rebuild(self, changed_keys: list[str]) -> None:
        keys = set(changed_keys)
        to_apply: dict = {}

        if keys & _LLM_KEYS:
            llm_factory = self._rebuild_callbacks.get("llm")
            parsers_factory = self._rebuild_callbacks.get("parsers")
            if llm_factory is None or parsers_factory is None:
                raise RuntimeError(
                    "LLM rebuild callback не задан (нужны 'llm' и 'parsers')"
                )
            new_llm = llm_factory()
            new_intent, new_resp = parsers_factory(new_llm)
            to_apply["intent_parser"] = new_intent
            to_apply["response_gen"] = new_resp

        if keys & _STT_KEYS:
            stt_factory = self._rebuild_callbacks.get("stt")
            if stt_factory is None:
                raise RuntimeError("STT rebuild callback не задан")
            to_apply["stt"] = stt_factory()

        if keys & _TTS_KEYS:
            tts_factory = self._rebuild_callbacks.get("tts")
            if tts_factory is None:
                raise RuntimeError("TTS rebuild callback не задан")
            to_apply["tts"] = tts_factory()

        if to_apply:
            self.core.replace_runtime_components(to_apply)
            print(
                f"[REBUILD] применены компоненты: {sorted(to_apply.keys())}",
                flush=True,
            )

        if keys & _CONTEXT_KEYS:
            ctx = getattr(self.core, "context", None)
            if ctx is not None:
                ctx.presentations_dir = Config.PRESENTATIONS_DIR
                ctx.presentation_match_threshold = float(
                    Config.PRESENTATION_MATCH_THRESHOLD
                )
                ctx.presentation_ambiguity_margin = float(
                    Config.PRESENTATION_AMBIGUITY_MARGIN
                )
                if hasattr(ctx, "gradebook_path"):
                    ctx.gradebook_path = Config.GRADEBOOK_PATH
                print(
                    f"[REBUILD] context: presentations_dir={ctx.presentations_dir!r} "
                    f"threshold={ctx.presentation_match_threshold} "
                    f"margin={ctx.presentation_ambiguity_margin} "
                    f"gradebook_path={getattr(ctx, 'gradebook_path', '?')!r}",
                    flush=True,
                )

    # ------------------------------------------------------------------
    def _on_segment(self, audio, sample_rate: int) -> None:
        print(
            f"[AUDIO] calling core.handle_audio "
            f"thread={threading.current_thread().name} "
            f"id={threading.get_ident()}",
            flush=True,
        )
        try:
            self.state_mgr.set(AssistantState.THINKING)

            def on_state(s: str) -> None:
                mapping = {
                    "Слушаю": AssistantState.LISTENING,
                    "Распознаю": AssistantState.THINKING,
                    "Обрабатываю": AssistantState.THINKING,
                    "Говорю": AssistantState.SPEAKING,
                    "Ожидание": AssistantState.IDLE,
                }
                st = mapping.get(s)
                if st is not None and st != AssistantState.WAITING_CONFIRMATION:
                    self.state_mgr.set(st)

            try:
                result = self.core.handle_audio(audio, sample_rate, on_state=on_state)
            except Exception:
                import traceback
                print("[AUDIO] exception inside core.handle_audio:", flush=True)
                traceback.print_exc()
                raise

            print(
                f"[AUDIO] core.handle_audio returned: "
                f"text={result.recognized_text!r} "
                f"addressed={result.is_addressed} "
                f"intents={[i.name for i in result.intents]} "
                f"final={result.final_speech!r}",
                flush=True,
            )

            if result.recognized_text:
                self.bus.publish(Event(
                    type=EventType.USER_MESSAGE,
                    payload={"text": result.recognized_text},
                ))

            if result.is_addressed and result.final_speech:
                self.bus.publish(Event(
                    type=EventType.ASSISTANT_MESSAGE,
                    payload={"text": result.final_speech},
                ))

            if getattr(self.core, "pending_confirmation", None) is not None:
                self.state_mgr.set(AssistantState.WAITING_CONFIRMATION)
            else:
                self.state_mgr.set(AssistantState.IDLE)
        except Exception as e:
            import traceback
            print("[AUDIO] exception in _on_segment:", flush=True)
            traceback.print_exc()
            self.bus.publish(Event(
                type=EventType.ERROR,
                payload={"text": str(e)},
            ))
            self.state_mgr.set(AssistantState.ERROR)


def run_app(core: AssistantCore, bus: EventBus, settings_store=None,
            rebuild_callbacks=None) -> None:
    app = QApplication.instance() or QApplication([])

    try:
        from assistant.logging_setup import install_gui_handler
        install_gui_handler()
    except Exception as e:
        print(f"[APP] GUI log handler install failed: {e}", flush=True)

    state_mgr = StateManager(bus)
    window = MainWindow(bus, settings_store=settings_store)

    application = Application(
        core, bus, state_mgr,
        settings_store=settings_store,
        rebuild_callbacks=rebuild_callbacks,
        window=window,
    )
    window._application = application

    application.rebuild_finished_sig.connect(window.on_rebuild_finished)

    window.show()
    app.exec()

    try:
        application.listener.stop()
    except Exception:
        pass
