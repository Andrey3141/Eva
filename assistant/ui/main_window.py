"""
MainWindow — полноэкранное окно с вертикальной страницей из секций.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMainWindow, QPushButton,
    QSizePolicy, QStackedWidget, QVBoxLayout, QWidget,
)

from ..events import EventBus, Event, EventType
from .avatar_view import AvatarView
from .chat_view import ChatView
from .log_view import LogView
from .settings_view import SettingsPanel
from .sidebar import Sidebar, SidebarController, PANEL_WIDTH
from .state_manager import AssistantState
from .scene_container import SceneContainer
from .theme import Palette, Spacing, app_qss

from config import Config


_STATE_LABELS = {
    AssistantState.IDLE: "Готова",
    AssistantState.LISTENING: "Слушаю",
    AssistantState.THINKING: "Думаю",
    AssistantState.SPEAKING: "Говорю",
    AssistantState.WAITING_CONFIRMATION: "Жду подтверждения",
    AssistantState.ERROR: "Ошибка",
}

_STATE_COLORS = {
    AssistantState.IDLE: Palette.OK,
    AssistantState.LISTENING: Palette.LISTEN,
    AssistantState.THINKING: Palette.THINK,
    AssistantState.SPEAKING: Palette.SPEAK,
    AssistantState.WAITING_CONFIRMATION: Palette.WARN,
    AssistantState.ERROR: Palette.ERR,
}


class MainWindow(QMainWindow):
    state_changed_sig = Signal(object)
    message_sig = Signal(str, str, bool)
    error_sig = Signal(str)

    PAGE_MAIN = 0
    PAGE_HISTORY = 1
    PAGE_ABOUT = 2

    def __init__(self, bus: EventBus, settings_store=None):
        super().__init__()
        self.bus = bus
        self._settings_store = settings_store
        self._state = AssistantState.IDLE
        self._is_fullscreen = False
        self._auto_fullscreen_done = False
        self._muted = True

        self.setWindowTitle("EVA — голосовой ассистент")
        self.setMinimumSize(720, 520)
        self.setStyleSheet(app_qss())

        self.state_changed_sig.connect(self._on_state_changed)
        self.message_sig.connect(self._on_message)
        self.error_sig.connect(self._on_error)

        bus.subscribe(EventType.ASSISTANT_STATE_CHANGED, self._bus_state)
        bus.subscribe(EventType.USER_MESSAGE, self._bus_user_message)
        bus.subscribe(EventType.ASSISTANT_MESSAGE, self._bus_assistant_message)
        bus.subscribe(EventType.ERROR, self._bus_error)
        bus.subscribe(EventType.CONFIG_CHANGED, self._bus_config_changed)
        bus.subscribe(EventType.MICROPHONE_MUTED_CHANGED, self._bus_mic_muted)

        self._settings_panel: SettingsPanel | None = None
        self._log_view: LogView | None = None
        self._about_avatar: AvatarView | None = None

        self._build_ui()
        self._build_sidebar()

        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, activated=self._on_escape)

        self._on_state_changed(self._state)
        self._apply_mic_button_state()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        ui_section = self._build_ui_section()
        self.scene = SceneContainer(ui_section=ui_section)
        self.setCentralWidget(self.scene)

    def _build_ui_section(self) -> QWidget:
        section = QWidget()
        root = QVBoxLayout(section)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header())
        root.addWidget(self._divider())

        self._stack = QStackedWidget()
        self._stack.setSizePolicy(QSizePolicy.Policy.Expanding,
                                  QSizePolicy.Policy.Expanding)
        self._stack.addWidget(self._build_main_page())
        self._stack.addWidget(self._build_history_page())
        self._stack.addWidget(self._build_about_page())

        root.addWidget(self._stack, 1)
        root.addWidget(self._divider())
        root.addWidget(self._build_footer())
        return section

    def _divider(self) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet(
            f"background: {Palette.BORDER_SOFT}; max-height: 1px; border: none;"
        )
        return line

    def _build_header(self) -> QWidget:
        header = QFrame()
        header.setStyleSheet(f"background: {Palette.SURFACE_LO};")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(Spacing.XL, Spacing.MD, Spacing.XL, Spacing.MD)
        layout.setSpacing(Spacing.MD)

        self._header_name = QLabel(Config.ASSISTANT_NAME)
        self._header_name.setProperty("role", "title")
        layout.addWidget(self._header_name)

        layout.addStretch(1)

        self._status_dot = QLabel("●")
        self._status_dot.setStyleSheet(f"color: {Palette.OK}; font-size: 16px;")
        layout.addWidget(self._status_dot)

        self._status_label = QLabel(_STATE_LABELS[self._state])
        self._status_label.setProperty("role", "dim")
        layout.addWidget(self._status_label)

        layout.addSpacing(Spacing.MD)

        self._menu_btn = QPushButton("☰")
        self._menu_btn.setProperty("role", "ghost")
        self._menu_btn.setFixedSize(32, 32)
        self._menu_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._menu_btn.clicked.connect(self._on_menu_clicked)
        layout.addWidget(self._menu_btn)

        return header

    def _build_main_page(self) -> QWidget:
        if self._settings_store is None:
            empty = QWidget()
            lay = QVBoxLayout(empty)
            msg = QLabel("SettingsStore не подключён")
            msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lay.addWidget(msg)
            return empty

        self._settings_panel = SettingsPanel(
            self._settings_store, bus=self.bus,
        )
        self._settings_panel.set_mute_state(self._muted)
        self._settings_panel.open_log_requested.connect(self._open_log_view)
        return self._settings_panel

    def _build_history_page(self) -> QWidget:
        self.chat = ChatView()
        return self.chat

    def _build_about_page(self) -> QWidget:
        import platform, sys
        from assistant import paths

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(Spacing.XXL, Spacing.XXL, Spacing.XXL, Spacing.XXL)
        layout.setSpacing(Spacing.MD)

        title = QLabel("EVA")
        title.setProperty("role", "title")
        layout.addWidget(title)

        self._about_sub = QLabel(
            f"{Config.ASSISTANT_NAME} · голосовой ассистент преподавателя"
        )
        self._about_sub.setProperty("role", "dim")
        layout.addWidget(self._about_sub)

        layout.addSpacing(Spacing.LG)

        # Avatar — реальный потребитель UI_ANIMATIONS_ENABLED.
        self._about_avatar = AvatarView(
            animations_enabled=bool(Config.UI_ANIMATIONS_ENABLED),
            parent=page,
        )
        self._about_avatar.setFixedSize(160, 160)
        layout.addWidget(self._about_avatar, 0, Qt.AlignmentFlag.AlignHCenter)

        layout.addSpacing(Spacing.LG)

        rows = [
            ("Версия", "EVA 0.1"),
            ("Python", sys.version.split()[0]),
            ("Платформа", platform.platform()),
            ("Runtime", paths.runtime_kind()),
            ("Логи", str(paths.logs_dir())),
            ("Настройки", str(paths.settings_path())),
        ]
        for label, value in rows:
            row = QHBoxLayout()
            k = QLabel(label)
            k.setProperty("role", "section")
            k.setFixedWidth(140)
            v = QLabel(str(value))
            v.setProperty("role", "dim")
            v.setWordWrap(True)
            row.addWidget(k)
            row.addWidget(v, 1)
            layout.addLayout(row)

        layout.addStretch(1)
        return page

    def _build_footer(self) -> QWidget:
        footer = QFrame()
        footer.setStyleSheet(f"background: {Palette.SURFACE_LO};")
        layout = QHBoxLayout(footer)
        layout.setContentsMargins(Spacing.XL, Spacing.MD, Spacing.XL, Spacing.MD)
        layout.setSpacing(Spacing.MD)

        self._footer_hint = QLabel("🎙  Микрофон выключен — включите в настройках")
        self._footer_hint.setProperty("role", "dim")
        layout.addWidget(self._footer_hint)
        layout.addStretch(1)

        self.mic_btn = QPushButton("🔇")
        self.mic_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mic_btn.setFixedSize(56, 56)
        self.mic_btn.clicked.connect(self._on_mic_clicked)
        layout.addWidget(self.mic_btn)

        return footer

    # ------------------------------------------------------------------
    def _apply_mic_button_state(self) -> None:
        if self._muted:
            self.mic_btn.setText("🔇")
            self.mic_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {Palette.ERR};
                    color: white;
                    border: none;
                    border-radius: 28px;
                    font-size: 22px;
                }}
                QPushButton:hover {{ background: #dc2626; }}
                QPushButton:pressed {{ background: #b91c1c; }}
            """)
            self._footer_hint.setText("🔇  Микрофон выключен — нажмите, чтобы включить")
        else:
            self.mic_btn.setText("🎙")
            self.mic_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {Palette.ACCENT};
                    color: white;
                    border: none;
                    border-radius: 28px;
                    font-size: 22px;
                }}
                QPushButton:hover {{ background: {Palette.ACCENT_HI}; }}
                QPushButton:pressed {{ background: {Palette.ACCENT_LO}; }}
            """)
            self._footer_hint.setText("🎙  Слушаю постоянно — говорите")

    # ------------------------------------------------------------------
    def _build_sidebar(self) -> None:
        self._sidebar = Sidebar(self, on_action=self._on_sidebar_action)
        self._sidebar.attach_to(self)
        self._sidebar_controller = SidebarController(self, self._sidebar)

    def _on_menu_clicked(self) -> None:
        if self.scene.current_section() == 0:
            self.scene.go_to_section(1)
        if self._sidebar.is_open():
            self._sidebar.hide_panel()
        else:
            self._sidebar.show_panel()

    def _on_sidebar_action(self, action: str) -> None:
        if action == "settings":
            self.scene.go_to_section(1)
            self._go_to(self.PAGE_MAIN)
        elif action == "history":
            self.scene.go_to_section(1)
            self._go_to(self.PAGE_HISTORY)
        elif action == "devices":
            self.scene.go_to_section(1)
            self._go_to(self.PAGE_MAIN)
        elif action == "about":
            self.scene.go_to_section(1)
            self._go_to(self.PAGE_ABOUT)
        elif action == "toggle_fullscreen":
            self._toggle_fullscreen()
        self._sidebar.hide_panel()

    def _go_to(self, page_index: int) -> None:
        self._stack.setCurrentIndex(page_index)

    # ------------------------------------------------------------------
    def _open_log_view(self) -> None:
        if self._log_view is None:
            self._log_view = LogView(parent=self)
        self._log_view.show()
        self._log_view.raise_()
        self._log_view.activateWindow()

    # ------------------------------------------------------------------
    def showEvent(self, event):
        super().showEvent(event)
        if not self._auto_fullscreen_done:
            self._auto_fullscreen_done = True
            QTimer.singleShot(0, self._enter_fullscreen)

    def _enter_fullscreen(self) -> None:
        self.showFullScreen()
        self._is_fullscreen = True
        self._sidebar.set_fullscreen(True)

    def _toggle_fullscreen(self) -> None:
        if self._is_fullscreen:
            self.showNormal()
            self._is_fullscreen = False
        else:
            self.showFullScreen()
            self._is_fullscreen = True
        self._sidebar.set_fullscreen(self._is_fullscreen)

    def _on_escape(self) -> None:
        if self._is_fullscreen:
            self.showNormal()
            self._is_fullscreen = False
            self._sidebar.set_fullscreen(False)

    # ------------------------------------------------------------------
    def _bus_state(self, event: Event) -> None:
        self.state_changed_sig.emit(event.payload.get("state"))

    def _bus_user_message(self, event: Event) -> None:
        self.message_sig.emit("Вы", event.payload.get("text", ""), True)

    def _bus_assistant_message(self, event: Event) -> None:
        self.message_sig.emit(Config.ASSISTANT_NAME, event.payload.get("text", ""), False)

    def _bus_error(self, event: Event) -> None:
        self.error_sig.emit(event.payload.get("text", "Ошибка"))

    def _bus_config_changed(self, event: Event) -> None:
        try:
            self._header_name.setText(Config.ASSISTANT_NAME)
            if hasattr(self, "_about_sub"):
                self._about_sub.setText(
                    f"{Config.ASSISTANT_NAME} · голосовой ассистент преподавателя"
                )
            if self._about_avatar is not None:
                self._about_avatar.set_animations_enabled(
                    bool(Config.UI_ANIMATIONS_ENABLED)
                )
        except Exception as e:
            print(f"[MainWindow] config changed error: {e}", flush=True)

    def _bus_mic_muted(self, event: Event) -> None:
        muted = bool(event.payload.get("muted", True))
        if muted == self._muted:
            return
        self._muted = muted
        self._apply_mic_button_state()
        if self._settings_panel is not None:
            try:
                self._settings_panel.set_mute_state(self._muted)
            except Exception:
                pass

    # ------------------------------------------------------------------
    def _on_state_changed(self, state) -> None:
        if state is None:
            return
        self._state = state
        self._status_label.setText(_STATE_LABELS.get(state, "—"))
        self._status_dot.setStyleSheet(
            f"color: {_STATE_COLORS.get(state, Palette.OK)}; font-size: 16px;"
        )

    def _on_message(self, author: str, text: str, is_user: bool) -> None:
        if hasattr(self, "chat"):
            self.chat.add_message(author, text, is_user)

    def _on_error(self, text: str) -> None:
        if hasattr(self, "chat"):
            self.chat.add_system(f"⚠ {text}")

    def _on_mic_clicked(self) -> None:
        new_muted = not self._muted
        self.bus.publish(Event(
            type=EventType.MICROPHONE_MUTED_CHANGED,
            payload={"muted": new_muted},
        ))

    def on_rebuild_finished(self, payload: dict) -> None:
        if self._settings_panel is None:
            return
        ok = bool(payload.get("ok"))
        error = str(payload.get("error") or "")
        self._settings_panel.show_rebuild_result(ok, error)

    # ------------------------------------------------------------------
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "_sidebar"):
            self._sidebar.setFixedHeight(self.height())
            if self._sidebar.is_open():
                self._sidebar.move(0, 0)
            else:
                self._sidebar.move(-PANEL_WIDTH, 0)

    def closeEvent(self, event):
        try:
            if hasattr(self, "scene"):
                self.scene.intro.stop()
        except Exception:
            pass
        super().closeEvent(event)
