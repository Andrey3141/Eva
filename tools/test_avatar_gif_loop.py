"""
Интеграционный UI-тест: зацикливание QMovie в аватаре
не должно вызывать пересчёт геометрии SceneContainer.

Проверяет связку:
  SceneContainer → _Section(ui_section) → AvatarView → GifRenderer → QMovie

Сценарий:
  1. SceneContainer с IntroView и ui_section, внутри которой AvatarView
     с GifRenderer.
  2. show(), processEvents() — даём layout примениться.
  3. Запоминаем высоты _s0 / _s1 и берём QMovie из GifRenderer.
  4. Эмулируем зацикливание: jumpToFrame(N-1) → processEvents →
     jumpToFrame(0) → processEvents.
  5. Убеждаемся:
     - _sync_section_heights не вызывался после начала перемотки кадра;
     - высоты _s0 / _s1 не изменились;
     - SceneContainer не трогал scrollbar.

Окно не показывается на экране (show() на QWidget без .show() ОС не создаёт
видимого окна), Qt работает в offscreen-режиме, если QT_QPA_PLATFORM=offscreen.
На CI это работает; локально тест тоже не откроет окно поверх других.

Запуск:
    python -m pytest tools/test_avatar_gif_loop.py -v
"""
from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest

# Offscreen — чтобы не открывать видимое окно и не требовать дисплея.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtCore import QSize

from assistant import paths


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


def _build_container_with_avatar(qapp):
    """
    Собирает SceneContainer с IntroView и ui_section, в которой находится
    AvatarView с GifRenderer (если доступен способ его туда положить).

    Возвращает (container, avatar_view, renderer_or_None).
    """
    from assistant.ui.scene_container import SceneContainer
    from assistant.ui.avatar_view import AvatarView
    from assistant.ui.avatar.gif_renderer import GifRenderer

    gif_path = paths.warp_gif_path()

    ui_section = QWidget()
    container = SceneContainer(ui_section=ui_section)

    avatar = AvatarView(parent=ui_section)
    avatar.resize(240, 240)

    renderer = None
    # Пробуем «нормальный» путь: AvatarView.set_renderer, если он есть.
    if hasattr(avatar, "set_renderer"):
        try:
            renderer = GifRenderer(gif_path)
            avatar.set_renderer(renderer)
        except Exception:
            renderer = None

    # Если у AvatarView нет set_renderer — создаём GifRenderer прямо
    # внутри ui_section, чтобы его QMovie всё равно был в дереве виджетов
    # SceneContainer.
    if renderer is None and gif_path.is_file():
        renderer = GifRenderer(gif_path)
        renderer.widget().setParent(ui_section)
        renderer.widget().resize(240, 240)
        renderer.widget().show()

    return container, avatar, renderer


def test_avatar_gif_loop_does_not_trigger_scene_resync(qapp):
    """
    Перемотка кадров QMovie в аватаре (эмуляция зацикливания)
    не должна вызывать _sync_section_heights / менять высоты секций.
    """
    gif_path = paths.warp_gif_path()
    if not gif_path.is_file():
        pytest.skip(f"Нет GIF: {gif_path}")

    container, avatar, renderer = _build_container_with_avatar(qapp)
    try:
        container.resize(1920, 1080)
        container.show()
        qapp.processEvents()

        # Дать layout и таймерам синглшот отработать.
        qapp.processEvents()

        if renderer is None or getattr(renderer, "_movie", None) is None:
            pytest.skip("GifRenderer с QMovie не создан — нечего проверять")

        movie = renderer._movie
        if not movie.isValid():
            pytest.skip("QMovie не открыл GIF")
        n = movie.frameCount()
        if n <= 0:
            pytest.skip("У GIF нет кадров")

        # Зафиксировать исходные высоты секций — до перемотки.
        h0_before = container._s0.height()
        h1_before = container._s1.height()

        # С этого момента любые вызовы _sync_section_heights должны
        # быть «не по нашей вине». Патчим метод и проверяем.
        with patch.object(container, "_sync_section_heights") as mock_sync:
            # Эмуляция зацикливания: перейти на последний кадр, потом на 0.
            movie.jumpToFrame(n - 1)
            qapp.processEvents()
            movie.jumpToFrame(0)
            qapp.processEvents()

            # Отдать шанс отложенным QTimer.singleShot(0, ...) сработать.
            qapp.processEvents()

            # 1. _sync_section_heights не должен был вызываться.
            assert mock_sync.call_count == 0, (
                f"_sync_section_heights вызван {mock_sync.call_count} раз "
                f"во время зацикливания GIF — это и есть пересчёт координат, "
                f"который видит пользователь."
            )

        # 2. Высоты секций не изменились.
        h0_after = container._s0.height()
        h1_after = container._s1.height()
        assert h0_after == h0_before, (
            f"_s0.height изменилась: {h0_before} → {h0_after}"
        )
        assert h1_after == h1_before, (
            f"_s1.height изменилась: {h1_before} → {h1_after}"
        )
    finally:
        try:
            if renderer is not None:
                renderer.stop()
                renderer.dispose()
        except Exception:
            pass
        try:
            container.deleteLater()
        except Exception:
            pass


def test_avatar_gif_loop_does_not_touch_scrollbar(qapp):
    """
    Дополнительный инвариант: во время зацикливания GIF
    ScrollBar SceneContainer не должен дёргаться.
    """
    gif_path = paths.warp_gif_path()
    if not gif_path.is_file():
        pytest.skip(f"Нет GIF: {gif_path}")

    container, avatar, renderer = _build_container_with_avatar(qapp)
    try:
        container.resize(1920, 1080)
        container.show()
        qapp.processEvents()
        qapp.processEvents()

        if renderer is None or getattr(renderer, "_movie", None) is None:
            pytest.skip("GifRenderer с QMovie не создан")

        movie = renderer._movie
        if not movie.isValid():
            pytest.skip("QMovie не открыл GIF")
        n = movie.frameCount()
        if n <= 0:
            pytest.skip("У GIF нет кадров")

        bar = container.verticalScrollBar()
        v_before = bar.value()

        movie.jumpToFrame(n - 1)
        qapp.processEvents()
        movie.jumpToFrame(0)
        qapp.processEvents()
        qapp.processEvents()

        v_after = bar.value()
        assert v_after == v_before, (
            f"ScrollBar дёрнулся: {v_before} → {v_after}. "
            f"Это значит, что-то в дереве виджетов триггерит snap/scroll."
        )
    finally:
        try:
            if renderer is not None:
                renderer.stop()
                renderer.dispose()
        except Exception:
            pass
        try:
            container.deleteLater()
        except Exception:
            pass
