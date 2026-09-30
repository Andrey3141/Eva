"""
AvatarView — контейнер аватара с безопасным переключением состояний.

Правила:
  - если для нового состояния нет подходящего файла —
    текущий renderer не трогаем;
  - если новый renderer не создался — текущий не трогаем;
  - переключение происходит ТОЛЬКО после успешного запуска нового.

Примечание: в текущей production-сборке EVA AvatarView не используется,
Hero-секция обслуживается IntroView. Модуль оставлен как отдельный
компонент для будущего.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QStackedLayout, QWidget

from .state_manager import AssistantState
from .avatar import AvatarRegistry, build_renderer_for


class _PlaceholderCanvas(QWidget):
    COLORS = {
        AssistantState.IDLE:                 QColor("#38bdf8"),
        AssistantState.LISTENING:            QColor("#22c55e"),
        AssistantState.THINKING:             QColor("#a855f7"),
        AssistantState.SPEAKING:             QColor("#ef4444"),
        AssistantState.WAITING_CONFIRMATION: QColor("#f59e0b"),
        AssistantState.ERROR:                QColor("#dc2626"),
    }

    def __init__(self, animations_enabled: bool = True, parent=None):
        super().__init__(parent)
        self._state = AssistantState.IDLE
        self._phase = 0.0
        self._animations_enabled = bool(animations_enabled)
        self.setMinimumSize(240, 240)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.setInterval(40)
        if self._animations_enabled:
            self._timer.start()

    def set_state(self, state: AssistantState) -> None:
        self._state = state
        self.update()

    def set_animations_enabled(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if enabled == self._animations_enabled:
            return
        self._animations_enabled = enabled
        if enabled:
            if not self._timer.isActive():
                self._timer.start()
        else:
            if self._timer.isActive():
                self._timer.stop()

    def _tick(self) -> None:
        speed = {
            AssistantState.IDLE: 0.02,
            AssistantState.LISTENING: 0.08,
            AssistantState.THINKING: 0.05,
            AssistantState.SPEAKING: 0.12,
            AssistantState.WAITING_CONFIRMATION: 0.06,
            AssistantState.ERROR: 0.02,
        }.get(self._state, 0.02)
        self._phase = (self._phase + speed) % 1.0
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)


class AvatarView(QWidget):
    def __init__(
        self,
        registry: AvatarRegistry | None = None,
        animations_enabled: bool = True,
        parent=None,
    ):
        super().__init__(parent)
        self.setMinimumSize(260, 260)

        self._registry = registry
        self._animations_enabled = bool(animations_enabled)
        self._state = AssistantState.IDLE
        self._current_renderer = None

        self._placeholder = _PlaceholderCanvas(
            animations_enabled=self._animations_enabled
        )
        self._stack = QStackedLayout(self)
        self._stack.setContentsMargins(0, 0, 0, 0)
        self._stack.addWidget(self._placeholder)
        self._stack.setCurrentWidget(self._placeholder)

        self.set_state(AssistantState.IDLE)

    # ------------------------------------------------------------------
    def set_animations_enabled(self, enabled: bool) -> None:
        enabled = bool(enabled)
        self._animations_enabled = enabled
        self._placeholder.set_animations_enabled(enabled)

    # ------------------------------------------------------------------
    def set_state(self, state: AssistantState) -> None:
        self._state = state
        self._placeholder.set_state(state)

        if self._registry is None:
            if self._current_renderer is None:
                self._show_placeholder()
            return

        file_path: Path | None = self._registry.file_for_state(state.value)

        if file_path is None:
            # Нет целевого файла — оставляем текущий renderer.
            if self._current_renderer is None:
                self._show_placeholder()
            return

        renderer = build_renderer_for(file_path)
        if renderer is None:
            if self._current_renderer is None:
                self._show_placeholder()
            return

        self._switch_renderer(renderer)

    # ------------------------------------------------------------------
    def _cleanup_current_renderer(self) -> None:
        if self._current_renderer is not None:
            try:
                self._current_renderer.stop()
                self._current_renderer.dispose()
            except Exception:
                pass

            widget = self._current_renderer.widget()
            if widget is not None:
                self._stack.removeWidget(widget)
                widget.setParent(None)
                widget.deleteLater()

            self._current_renderer = None

    def _discard_renderer(self, renderer) -> None:
        """Удаляет не принятый renderer, не трогая текущий."""
        if renderer is None:
            return
        try:
            renderer.stop()
            renderer.dispose()
        except Exception:
            pass
        try:
            widget = renderer.widget()
        except Exception:
            widget = None
        if widget is not None:
            try:
                self._stack.removeWidget(widget)
            except Exception:
                pass
            widget.setParent(None)
            widget.deleteLater()

    def _switch_renderer(self, renderer) -> None:
        """
        Безопасное переключение:
          1. Готовим виджет нового renderer.
          2. Добавляем его в стек, делаем видимым, запускаем.
          3. Если запуск не удался — удаляем новый, старый оставляем.
          4. Если запуск удался — останавливаем и удаляем старый.
        """
        new_widget = renderer.widget()
        if new_widget is None:
            # Пустой renderer — не трогаем текущий.
            self._discard_renderer(renderer)
            return

        old_renderer = self._current_renderer
        old_widget = old_renderer.widget() if old_renderer is not None else None

        # 1. Добавляем новый виджет в стек и делаем видимым.
        try:
            self._stack.addWidget(new_widget)
            self._stack.setCurrentWidget(new_widget)
        except Exception as e:
            print(f"[AVATAR] failed to add new renderer widget: {e}",
                  flush=True)
            self._discard_renderer(renderer)
            return

        # 2. Пытаемся запустить.
        started = False
        try:
            renderer.start()
            started = True
        except Exception as e:
            print(f"[AVATAR] new renderer.start() failed: {e}", flush=True)
            started = False

        if not started:
            # 3. Новый не запустился — удаляем новый, возвращаем старый.
            try:
                self._stack.removeWidget(new_widget)
            except Exception:
                pass
            self._discard_renderer(renderer)
            if old_widget is not None:
                try:
                    self._stack.setCurrentWidget(old_widget)
                except Exception:
                    pass
            return

        # 4. Новый запустился — теперь можно остановить старый.
        self._current_renderer = renderer
        if old_renderer is not None:
            try:
                old_renderer.stop()
                old_renderer.dispose()
            except Exception:
                pass
            if old_widget is not None:
                try:
                    self._stack.removeWidget(old_widget)
                except Exception:
                    pass
                old_widget.setParent(None)
                old_widget.deleteLater()

    def _show_placeholder(self) -> None:
        self._cleanup_current_renderer()
        self._stack.setCurrentWidget(self._placeholder)
