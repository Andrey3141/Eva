"""
ChatView — история текущего диалога за запуск EVA.
Session-only: при закрытии приложения история исчезает.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve
from PySide6.QtWidgets import (
    QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QScrollArea,
    QSizePolicy, QVBoxLayout, QWidget,
)

from .theme import Palette, Radius, Spacing


Role = Literal["user", "assistant", "system"]


class _MessageCard(QFrame):
    """
    Карточка одного сообщения.
    user  — выровнена вправо, синий акцент.
    assistant — выровнена влево, нейтральная.
    system — по центру, приглушённая.
    """

    def __init__(self, role: Role, text: str, timestamp: datetime | None = None,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("messageCard")
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Minimum)

        ts = (timestamp or datetime.now()).strftime("%H:%M")
        author = {"user": "Вы", "assistant": "Алеся", "system": "система"}[role]

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(4)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)

        name = QLabel(author)
        name.setProperty("role", "section")
        header.addWidget(name)

        header.addStretch(1)

        stamp = QLabel(ts)
        stamp.setProperty("role", "dim")
        header.addWidget(stamp)

        layout.addLayout(header)

        body = QLabel(text)
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        body.setProperty("role", "body")
        body.setMaximumWidth(720)
        layout.addWidget(body)

        self._apply_style(role)
        self._fade_in()

    def _apply_style(self, role: Role) -> None:
        if role == "user":
            bg = Palette.USER_BUBBLE
            border = Palette.USER_BUBBLE_HI
            align = Qt.AlignmentFlag.AlignRight
        elif role == "assistant":
            bg = Palette.ASSISTANT_BUBBLE
            border = Palette.BORDER_SOFT
            align = Qt.AlignmentFlag.AlignLeft
        else:
            bg = Palette.SURFACE_LO
            border = Palette.BORDER_SOFT
            align = Qt.AlignmentFlag.AlignHCenter

        self.setStyleSheet(f"""
            QFrame#messageCard {{
                background: {bg};
                border: 1px solid {border};
                border-radius: {Radius.MD}px;
            }}
            QFrame#messageCard QLabel[role="body"] {{
                color: {Palette.TEXT};
                font-size: 13px;
            }}
        """)

        # Выравнивание карточки задаёт внешний layout, а не сама карточка.
        self.setProperty("align", int(align))

    def _fade_in(self) -> None:
        eff = QGraphicsOpacityEffect(self)
        eff.setOpacity(0.0)
        self.setGraphicsEffect(eff)
        anim = QPropertyAnimation(eff, b"opacity", self)
        anim.setDuration(220)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)


class ChatView(QScrollArea):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._container = QWidget()
        self._container.setObjectName("chatContainer")
        self._layout = QVBoxLayout(self._container)
        self._layout.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG)
        self._layout.setSpacing(Spacing.MD)
        self._layout.addStretch(1)

        self.setWidget(self._container)

    # ------------------------------------------------------------------
    def add_message(self, author: str, text: str, is_user: bool) -> None:
        """
        Совместимо с существующим вызовом из MainWindow:
        add_message(author, text, is_user).
        """
        role: Role = "user" if is_user else "assistant"
        self._add(role, text)

    def add_system(self, text: str) -> None:
        self._add("system", text)

    def clear(self) -> None:
        while self._layout.count() > 1:
            item = self._layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    # ------------------------------------------------------------------
    def _add(self, role: Role, text: str) -> None:
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(0)

        card = _MessageCard(role, text)

        if role == "user":
            row_layout.addStretch(1)
            row_layout.addWidget(card)
        elif role == "assistant":
            row_layout.addWidget(card)
            row_layout.addStretch(1)
        else:
            row_layout.addStretch(1)
            row_layout.addWidget(card)
            row_layout.addStretch(1)

        # Вставляем перед stretch
        self._layout.insertWidget(self._layout.count() - 1, row)

        # Автоскролл после layout
        QTimer.singleShot(0, self._scroll_to_bottom)

    def _scroll_to_bottom(self) -> None:
        bar = self.verticalScrollBar()
        bar.setValue(bar.maximum())
