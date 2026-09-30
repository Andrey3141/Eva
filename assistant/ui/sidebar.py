"""
Sidebar — скрытая панель слева, overlay поверх всего окна.

Trigger-зона — 8 px у левого края.
Панель выезжает с animation, уезжает через HOLD_MS после ухода мыши.
Работает в обычном, maximized и fullscreen режимах.
"""
from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import (
    Qt, QEvent, QObject, QPoint, QPropertyAnimation, QEasingCurve, QTimer, QRect,
)
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from .theme import Palette, Radius, Spacing


TRIGGER_WIDTH = 8
PANEL_WIDTH = 260
ANIM_MS = 200
HOLD_MS = 400


class Sidebar(QFrame):
    def __init__(self, parent: QWidget, on_action: Callable[[str], None]):
        super().__init__(parent)
        self._on_action = on_action
        self.setObjectName("sidebar")
        self.setFixedWidth(PANEL_WIDTH)
        self.setStyleSheet(f"""
            QFrame#sidebar {{
                background: {Palette.SURFACE};
                border-right: 1px solid {Palette.BORDER};
            }}
            QLabel[role="title"] {{
                color: {Palette.TEXT};
                font-size: 14px;
                font-weight: 700;
                letter-spacing: 0.4px;
            }}
            QLabel[role="subtitle"] {{
                color: {Palette.TEXT_MUTED};
                font-size: 10px;
                letter-spacing: 0.8px;
            }}
            QPushButton[role="navitem"] {{
                background: transparent;
                border: 1px solid transparent;
                border-radius: {Radius.SM}px;
                color: {Palette.TEXT};
                text-align: left;
                padding: 10px 14px;
                font-size: 13px;
            }}
            QPushButton[role="navitem"]:hover {{
                background: {Palette.SURFACE_HI};
                border-color: {Palette.BORDER_SOFT};
            }}
            QPushButton[role="navitem"]:pressed {{
                background: {Palette.SURFACE_LO};
            }}
        """)

        self._build_ui()

        self._anim = QPropertyAnimation(self, b"pos", self)
        self._anim.setDuration(ANIM_MS)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.setInterval(HOLD_MS)
        self._hide_timer.timeout.connect(self._maybe_hide)

        self._is_open = False
        self._is_fullscreen = False
        self._parent_window: Optional[QWidget] = None

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.XL, Spacing.LG, Spacing.LG)
        layout.setSpacing(Spacing.MD)

        brand = QLabel("EVA")
        brand.setProperty("role", "title")
        layout.addWidget(brand)

        hint = QLabel("голосовой ассистент")
        hint.setProperty("role", "subtitle")
        layout.addWidget(hint)

        layout.addSpacing(Spacing.LG)

        for label, action in (
            ("Настройки", "settings"),
            ("История", "history"),
            ("Устройства", "devices"),
            ("О EVA", "about"),
        ):
            btn = QPushButton(label)
            btn.setProperty("role", "navitem")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _=False, a=action: self._emit(a))
            layout.addWidget(btn)

        layout.addStretch(1)

        self._fs_btn = QPushButton("⛶  Полный экран")
        self._fs_btn.setProperty("role", "navitem")
        self._fs_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._fs_btn.clicked.connect(lambda: self._emit("toggle_fullscreen"))
        layout.addWidget(self._fs_btn)

        version = QLabel("EVA · v0.1")
        version.setProperty("role", "subtitle")
        layout.addWidget(version)

    def _emit(self, action: str) -> None:
        self._on_action(action)

    # ------------------------------------------------------------------
    def attach_to(self, window: QWidget) -> None:
        self._parent_window = window
        self.setFixedHeight(window.height())
        self.move(-PANEL_WIDTH, 0)
        self.hide()

    def _hidden_pos(self) -> QPoint:
        return QPoint(-PANEL_WIDTH, 0)

    def _visible_pos(self) -> QPoint:
        return QPoint(0, 0)

    def show_panel(self) -> None:
        if self._parent_window is None:
            return
        self.setFixedHeight(self._parent_window.height())
        self.move(self._hidden_pos())
        self.show()
        self.raise_()
        self._anim.stop()
        self._anim.setStartValue(self.pos())
        self._anim.setEndValue(self._visible_pos())
        self._anim.start()
        self._is_open = True

    def hide_panel(self) -> None:
        if self._parent_window is None:
            return
        self._anim.stop()
        self._anim.setStartValue(self.pos())
        self._anim.setEndValue(self._hidden_pos())
        self._anim.start()
        self._is_open = False

    def toggle_panel(self) -> None:
        if self._is_open:
            self.hide_panel()
        else:
            self.show_panel()

    def is_open(self) -> bool:
        return self._is_open

    # ------------------------------------------------------------------
    def set_fullscreen(self, fullscreen: bool) -> None:
        self._is_fullscreen = fullscreen
        self._fs_btn.setText("⛶  Выйти из полного экрана" if fullscreen
                             else "⛶  Полный экран")

    # ------------------------------------------------------------------
    def _maybe_hide(self) -> None:
        if not self._is_open:
            return
        local = self.mapFromGlobal(QCursor.pos())
        if not self.rect().contains(local):
            self.hide_panel()

    # ------------------------------------------------------------------
    def enterEvent(self, event):
        self._hide_timer.stop()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hide_timer.start()
        super().leaveEvent(event)


class SidebarController(QObject):
    """
    Event filter на QMainWindow: ловит наведение на левый край окна
    и предлагает открыть sidebar.
    """

    def __init__(self, window: QWidget, sidebar: Sidebar):
        super().__init__(window)
        self._window = window
        self._sidebar = sidebar
        window.installEventFilter(self)

    def eventFilter(self, obj, event):
        if obj is not self._window:
            return False

        et = event.type()

        if et in (QEvent.Type.MouseMove, QEvent.Type.Enter):
            local = self._window.mapFromGlobal(QCursor.pos())
            if 0 <= local.x() <= TRIGGER_WIDTH and not self._sidebar.is_open():
                self._sidebar.show_panel()

        if et == QEvent.Type.Resize:
            self._sidebar.setFixedHeight(self._window.height())
            if self._sidebar.is_open():
                self._sidebar.move(0, 0)
            else:
                self._sidebar.move(-PANEL_WIDTH, 0)

        if et == QEvent.Type.Leave:
            if self._sidebar.is_open():
                self._sidebar._hide_timer.start()

        return False
