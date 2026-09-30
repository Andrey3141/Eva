"""
SceneContainer — вертикально прокручиваемая страница из полноэкранных секций.

Ключевое:
  - каждая секция имеет ФИКСИРОВАННУЮ высоту = viewport.height();
  - _root получает высоту 2 * viewport.height();
  - значит вертикальный scrollbar имеет range 0..viewport.height();
  - intro-секция — ровно на экран, UI-секция — строго ниже.

Защита от sizeHint-прыжка на старте:
  - _s0 / _s1 получают setFixedHeight(0) в __init__, чтобы layout
    не подставлял sizeHint содержимого (68 px / 36 px в логах);
  - _sync_section_heights() вызывается СИНХРОННО в resizeEvent —
    финальная высота применяется в том же цикле отрисовки;
  - _snap_to_current() вынесен в отдельный отложенный QTimer.singleShot,
    чтобы не блокировать синхронный пересчёт высот;
  - _is_resizing защищает от реентерабельных вызовов.

Snap-логика:
  - wheel down с секции 0 → плавный переход к секции 1;
  - wheel up с секции 1 → плавный возврат к секции 0;
  - при resize текущая секция сохраняется.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QTimer
from PySide6.QtWidgets import (
    QFrame, QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from .intro_view import IntroView


class _Section(QWidget):
    """
    Контейнер секции. Высота задаётся извне через setFixedHeight().
    Внутренние отступы и spacing — нулевые.
    """

    def __init__(self, inner: QWidget, parent: QWidget | None = None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(inner, 1)

        self._inner = inner


class SceneContainer(QScrollArea):
    SNAP_MS = 320

    def __init__(self, ui_section: QWidget, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._root = QWidget()
        self._root.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self._root_layout = QVBoxLayout(self._root)
        self._root_layout.setContentsMargins(0, 0, 0, 0)
        self._root_layout.setSpacing(0)

        self.intro = IntroView()
        self.ui_section = ui_section

        self._s0 = _Section(self.intro)
        self._s1 = _Section(self.ui_section)

        # Ключевая правка: НЕ даём layout подставить sizeHint содержимого
        # (68 px / 36 px). Первый layout увидит нули, финальная высота
        # будет выставлена синхронно в resizeEvent.
        self._s0.setFixedHeight(0)
        self._s1.setFixedHeight(0)

        self._root_layout.addWidget(self._s0)
        self._root_layout.addWidget(self._s1)

        self._root.setFixedHeight(0)

        self.setWidget(self._root)

        self._anim = QPropertyAnimation(self.verticalScrollBar(), b"value", self)
        self._anim.setDuration(self.SNAP_MS)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutCubic)

        # Защита от реентерабельного пересчёта геометрии.
        self._is_resizing = False
        self._current_section = 0

        # Никаких QTimer.singleShot для _sync_section_heights из __init__.
        # Синхронный вызов произойдёт в первом resizeEvent, когда
        # viewport().height() станет > 0.

    # ------------------------------------------------------------------
    def _section_height(self) -> int:
        return max(1, self.viewport().height())

    def _target_value(self, section: int) -> int:
        return section * self._section_height()

    def _animate_to(self, value: int) -> None:
        self._anim.stop()
        self._anim.setStartValue(self.verticalScrollBar().value())
        self._anim.setEndValue(value)
        self._anim.start()

    def go_to_section(self, section: int) -> None:
        section = max(0, min(1, section))
        self._current_section = section
        self._animate_to(self._target_value(section))

    def current_section(self) -> int:
        return self._current_section

    # ------------------------------------------------------------------
    def _sync_section_heights(self) -> None:
        """
        Жёстко фиксируем высоты секций = высоте viewport.
        Вызывается синхронно из resizeEvent — чтобы финальные высоты
        применились до того, как layout отрисует промежуточный кадр.
        """
        h = self.viewport().height()
        if h <= 0:
            return
        if self._s0.height() == h and self._s1.height() == h:
            return
        self._s0.setFixedHeight(h)
        self._s1.setFixedHeight(h)
        self._root.setFixedHeight(h * 2)

    # ------------------------------------------------------------------
    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if delta == 0:
            super().wheelEvent(event)
            return

        v = self.verticalScrollBar().value()
        h = self._section_height()
        nearest = 0 if (v < h // 2) else 1

        if delta < 0 and nearest == 0:
            self.go_to_section(1)
            event.accept()
            return
        if delta > 0 and nearest == 1:
            self.go_to_section(0)
            event.accept()
            return
        super().wheelEvent(event)

    # ------------------------------------------------------------------
    def showEvent(self, event):
        super().showEvent(event)
        # Ничего не делаем с геометрией при показе — высоты будут
        # выставлены синхронно в первом resizeEvent.

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # СИНХРОННЫЙ пересчёт высот — в том же цикле отрисовки,
        # до того как layout успеет показать промежуточный кадр.
        if not self._is_resizing:
            self._is_resizing = True
            try:
                self._sync_section_heights()
            finally:
                self._is_resizing = False

        # Snap — откладываем, чтобы не блокировать синхронную
        # синхронизацию высот и не дёргать scrollbar прямо сейчас.
        QTimer.singleShot(0, self._snap_to_current)

    def _snap_to_current(self) -> None:
        bar = self.verticalScrollBar()
        if bar.maximum() <= 0:
            return
        target = self._target_value(self._current_section)
        if bar.value() != target:
            bar.setValue(target)
