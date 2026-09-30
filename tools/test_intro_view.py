"""
Тесты IntroView — новая архитектура через _MediaLayer.

Группы:
  1. Изолированные тесты геометрии _MediaLayer (nativeSize задан явно).
  2. Реальные production-тесты IntroView + assets/avatar/warp.mp4.
  3. Интеграционный тест реальной цепочки MainWindow → SceneContainer
     → IntroView с диагностикой размеров и видимости.
  4. Интеграционный тест реального перехода preview → warp через
     production-механизм IntroView._start() / EndOfMedia / _apply_state_to_view.

Запуск в offscreen-режиме.
"""
from __future__ import annotations

import os
import sys
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout
from PySide6.QtCore import QSizeF, Qt, QEventLoop, QTimer


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


@pytest.fixture
def isolated_paths(tmp_path, monkeypatch):
    import assistant.paths as paths_mod
    monkeypatch.setattr(paths_mod, "preview_video_path",
                        lambda: tmp_path / "preview.mp4")
    monkeypatch.setattr(paths_mod, "warp_video_path",
                        lambda: tmp_path / "warp.mp4")
    monkeypatch.setattr(paths_mod, "speaks_video_path",
                        lambda: tmp_path / "speaks.mp4")
    monkeypatch.setattr(paths_mod, "thinks_video_path",
                        lambda: tmp_path / "thinks.mp4")
    return tmp_path


# ---------------------------------------------------------------------------
# 1. Hero занимает 100% viewport
# ---------------------------------------------------------------------------

def _assert_full_viewport(view, w: int, h: int):
    view.resize(w, h)
    qapp = QApplication.instance()
    if qapp is not None:
        qapp.processEvents()
        qapp.processEvents()
    assert view.width() == w
    assert view.height() == h


@pytest.mark.parametrize("w,h", [
    (1920, 1080),
    (1280, 720),
    (1080, 1920),
])
def test_hero_full_viewport(qapp, w, h, isolated_paths):
    from assistant.ui.intro_view import IntroView
    view = IntroView(autostart=False)
    try:
        _assert_full_viewport(view, w, h)
        assert not hasattr(view, "_box")
        assert not hasattr(view, "_sync_box_geometry")
        assert not hasattr(view, "_compute_media_size")
    finally:
        view.deleteLater()


# ---------------------------------------------------------------------------
# 2. Отсутствие старых полей
# ---------------------------------------------------------------------------

def test_no_legacy_video_attributes(qapp, isolated_paths):
    from assistant.ui.intro_view import IntroView
    v = IntroView(autostart=False)
    try:
        for name in ("_video_view", "_video_item", "_video_scene",
                     "_movie", "_gif_label", "_gif_container",
                     "_video_container", "_gif_src_size",
                     "_gif_scaled_size"):
            assert not hasattr(v, name), f"Legacy attr present: {name}"
    finally:
        v.deleteLater()


# ---------------------------------------------------------------------------
# 3. _target_layer_key без файлов
# ---------------------------------------------------------------------------

def test_target_layer_key_no_files(qapp, isolated_paths):
    from assistant.ui.intro_view import IntroView
    from assistant.ui.state_manager import AssistantState
    v = IntroView(autostart=False)
    try:
        v.set_state(AssistantState.IDLE)
        assert v._target_layer_key() == "warp"

        v.set_state(AssistantState.SPEAKING)
        assert v._target_layer_key() == "speaks"

        v.set_state(AssistantState.THINKING)
        assert v._target_layer_key() == "thinks"

        v.set_state(AssistantState.ERROR)
        assert v._target_layer_key() == "warp"
    finally:
        v.deleteLater()


# ---------------------------------------------------------------------------
# 4. _MediaLayer.sync_view через layout (изолированный контракт)
# ---------------------------------------------------------------------------

def _make_media_layer(qapp, tmp_path, *, native_w, native_h,
                     window_w=800, window_h=600):
    try:
        from PySide6.QtMultimediaWidgets import QGraphicsVideoItem
    except Exception:
        pytest.skip("QtMultimediaWidgets недоступен")

    from PySide6.QtWidgets import QGraphicsView, QGraphicsScene, QFrame
    from PySide6.QtGui import QBrush, QColor
    from PySide6.QtCore import QRectF

    from assistant.ui.intro_view import _MediaLayer

    parent = QWidget()
    parent.resize(window_w, window_h)

    outer_layout = QVBoxLayout(parent)
    outer_layout.setContentsMargins(0, 0, 0, 0)
    outer_layout.setSpacing(0)

    layer = _MediaLayer.__new__(_MediaLayer)
    layer.video_path = tmp_path / "video.mp4"
    layer.loop = True

    layer.container = QWidget(parent)
    container_layout = QVBoxLayout(layer.container)
    container_layout.setContentsMargins(0, 0, 0, 0)
    container_layout.setSpacing(0)

    layer.view = QGraphicsView(layer.container)
    layer.view.setFrameShape(QFrame.Shape.NoFrame)
    layer.view.setHorizontalScrollBarPolicy(
        Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    )
    layer.view.setVerticalScrollBarPolicy(
        Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    )
    layer.view.setAlignment(Qt.AlignmentFlag.AlignCenter)

    layer.scene = QGraphicsScene()
    layer.scene.setBackgroundBrush(QBrush(QColor("#ffffff")))
    layer.scene.setSceneRect(QRectF(0, 0, 1, 1))
    layer.view.setScene(layer.scene)

    layer.item = QGraphicsVideoItem()
    layer.scene.addItem(layer.item)

    layer.item.nativeSize = lambda: QSizeF(native_w, native_h)
    layer.item.setSize(QSizeF(native_w, native_h))
    layer.item.setPos(0, 0)

    layer.player = None
    layer.audio = None
    layer._error_seen = ""

    container_layout.addWidget(layer.view, 1)
    outer_layout.addWidget(layer.container)

    parent.show()
    qapp.processEvents()
    qapp.processEvents()

    return layer, parent


def test_media_layer_sync_view_uses_fit_in_view(qapp, tmp_path):
    native_w, native_h = 990, 1280
    layer, parent = _make_media_layer(
        qapp, tmp_path, native_w=native_w, native_h=native_h,
        window_w=800, window_h=600,
    )
    try:
        vp = layer.view.viewport()
        vw = vp.width()
        vh = vp.height()
        assert vw > 0
        assert vh > 0

        layer.sync_view()
        qapp.processEvents()

        view = layer.view
        item = layer.item
        t = view.transform()

        scene_rect = item.mapRectToScene(item.boundingRect())
        mapped = view.mapFromScene(scene_rect).boundingRect()
        vr = vp.rect()

        expected_scale = max(vw / native_w, vh / native_h)

        diag = (
            f"\n[FIT-IN-VIEW DIAGNOSTIC]"
            f"\n  viewport       = ({vw}, {vh})"
            f"\n  native         = ({native_w}, {native_h})"
            f"\n  transform.m11  = {t.m11():.4f}"
            f"\n  transform.m22  = {t.m22():.4f}"
            f"\n  expected_scale = {expected_scale:.4f}"
            f"\n  mapped         = {mapped}"
            f"\n  viewport.rect  = {vr}"
        )

        assert abs(t.m11() - expected_scale) < 0.01, diag
        assert abs(t.m22() - expected_scale) < 0.01, diag
        assert abs(t.m11() - t.m22()) <= 1e-6, diag

        expected_ar = native_w / native_h
        actual_ar = mapped.width() / mapped.height()
        assert abs(actual_ar - expected_ar) < 0.01, diag

        assert mapped.width() >= vr.width() - 4, diag
        assert mapped.height() >= vr.height() - 4, diag

        viewport_ar = vw / vh
        if abs(expected_ar - viewport_ar) > 0.01:
            wider = mapped.width() > vr.width() + 1
            taller = mapped.height() > vr.height() + 1
            assert wider or taller, diag

        assert abs(mapped.center().x() - vr.center().x()) <= 2, diag
        assert abs(mapped.center().y() - vr.center().y()) <= 2, diag
    finally:
        try:
            parent.deleteLater()
        except Exception:
            pass


def test_media_layer_scene_rect_is_displayable(qapp, tmp_path):
    layer, parent = _make_media_layer(
        qapp, tmp_path, native_w=990, native_h=1280,
        window_w=800, window_h=600,
    )
    try:
        layer.sync_view()
        qapp.processEvents()

        item_scene_rect = layer.item.mapRectToScene(
            layer.item.boundingRect()
        )
        sr = layer.scene.sceneRect()

        assert sr.width() > 0
        assert sr.height() > 0
        assert sr.contains(item_scene_rect)
    finally:
        try:
            parent.deleteLater()
        except Exception:
            pass


def test_media_layer_scrollbars_disabled(qapp, tmp_path):
    layer, parent = _make_media_layer(
        qapp, tmp_path, native_w=990, native_h=1280,
        window_w=800, window_h=600,
    )
    try:
        assert layer.view.horizontalScrollBarPolicy() == (
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        assert layer.view.verticalScrollBarPolicy() == (
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
    finally:
        try:
            parent.deleteLater()
        except Exception:
            pass


def test_media_layer_resyncs_on_resize(qapp, tmp_path):
    layer, parent = _make_media_layer(
        qapp, tmp_path, native_w=990, native_h=1280,
        window_w=800, window_h=600,
    )
    try:
        layer.sync_view()
        qapp.processEvents()
        t1 = layer.view.transform()
        m11_before = t1.m11()
        m22_before = t1.m22()

        parent.resize(400, 400)
        qapp.processEvents()
        qapp.processEvents()

        layer.sync_view()
        qapp.processEvents()
        t2 = layer.view.transform()
        m11_after = t2.m11()
        m22_after = t2.m22()

        assert (
            abs(m11_before - m11_after) > 1e-6
            or abs(m22_before - m22_after) > 1e-6
        ), (
            f"transform не пересчитан после resize: "
            f"до m11={m11_before}, m22={m22_before}; "
            f"после m11={m11_after}, m22={m22_after}"
        )
    finally:
        try:
            parent.deleteLater()
        except Exception:
            pass


def test_media_layer_centered(qapp, tmp_path):
    layer, parent = _make_media_layer(
        qapp, tmp_path, native_w=990, native_h=1280,
        window_w=800, window_h=600,
    )
    try:
        layer.sync_view()
        qapp.processEvents()

        mapped = layer.view.mapFromScene(
            layer.item.mapRectToScene(layer.item.boundingRect())
        ).boundingRect()
        vp_center = layer.view.viewport().rect().center()
        assert abs(mapped.center().x() - vp_center.x()) <= 2
        assert abs(mapped.center().y() - vp_center.y()) <= 2
    finally:
        try:
            parent.deleteLater()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# 5. Реальный production-тест: warp.mp4 через IntroView
# ---------------------------------------------------------------------------

def _pump_events(qapp, ms: int) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()
    qapp.processEvents()


def _wait_for_native_size(qapp, item, timeout_ms: int = 5000) -> QSizeF:
    deadline = time.monotonic() + timeout_ms / 1000.0
    size = item.nativeSize()
    while time.monotonic() < deadline:
        qapp.processEvents()
        size = item.nativeSize()
        if size.width() > 0 and size.height() > 0:
            return size
        _pump_events(qapp, 50)
    return item.nativeSize()


def _wait_for_condition(qapp, predicate, timeout_ms: int = 15000,
                        interval_ms: int = 50) -> bool:
    """
    Прокручивает event loop до тех пор, пока predicate() не вернёт True
    или не истечёт timeout. Возвращает True при успехе.
    """
    deadline = time.monotonic() + timeout_ms / 1000.0
    while time.monotonic() < deadline:
        qapp.processEvents()
        try:
            if predicate():
                return True
        except Exception:
            pass
        _pump_events(qapp, interval_ms)
    return False


def test_real_intro_view_warp_fills_viewport(qapp):
    from assistant import paths
    from assistant.ui.intro_view import IntroView, _HAVE_MULTIMEDIA

    if not _HAVE_MULTIMEDIA:
        pytest.skip("QtMultimedia недоступен в тестовом окружении")

    warp_path = paths.warp_video_path()
    if not warp_path.is_file():
        pytest.skip(f"Нет реального файла: {warp_path}")

    intro = IntroView(autostart=False)
    intro.resize(800, 600)
    intro.show()
    qapp.processEvents()

    try:
        warp_layer = intro._get_layer("warp")
        if warp_layer is None:
            pytest.skip("Не удалось создать _MediaLayer для warp.mp4")

        started = warp_layer.start_play()
        if not started:
            pytest.skip("warp.mp4 существует, но player не запустил его")

        item = warp_layer.item
        view = warp_layer.view

        native = _wait_for_native_size(qapp, item, timeout_ms=5000)
        if native.width() <= 0 or native.height() <= 0:
            pytest.skip(
                "QGraphicsVideoItem.nativeSize() не заполнился: "
                "Qt Multimedia в тестовом окружении не загрузил MP4"
            )

        _pump_events(qapp, 100)

        vp = view.viewport()
        vw = vp.width()
        vh = vp.height()
        if vw <= 0 or vh <= 0:
            pytest.skip(f"viewport не получил размер: ({vw}, {vh})")

        warp_layer.sync_view()
        qapp.processEvents()
        _pump_events(qapp, 50)

        t = view.transform()
        expected_scale = max(vw / native.width(), vh / native.height())

        scene_rect = item.mapRectToScene(item.boundingRect())
        mapped = view.mapFromScene(scene_rect).boundingRect()
        vr = vp.rect()

        diag = (
            f"\n[REAL WARP DIAGNOSTIC]"
            f"\n  warp file      = {warp_path}"
            f"\n  nativeSize     = ({native.width()}, {native.height()})"
            f"\n  viewport       = ({vw}, {vh})"
            f"\n  transform.m11  = {t.m11():.4f}"
            f"\n  transform.m22  = {t.m22():.4f}"
            f"\n  expected_scale = {expected_scale:.4f}"
            f"\n  mapped         = {mapped}"
            f"\n  viewport.rect  = {vr}"
        )

        assert abs(t.m11() - expected_scale) < 0.01, diag
        assert abs(t.m22() - expected_scale) < 0.01, diag
        assert abs(t.m11() - t.m22()) <= 1e-6, diag
        assert mapped.width() >= vr.width() - 4, diag
        assert mapped.height() >= vr.height() - 4, diag
        assert abs(mapped.center().x() - vr.center().x()) <= 2, diag
        assert abs(mapped.center().y() - vr.center().y()) <= 2, diag
    finally:
        try:
            intro.stop()
        except Exception:
            pass
        try:
            intro.deleteLater()
        except Exception:
            pass
        qapp.processEvents()


def test_real_intro_view_visible_warp_diagnostic(qapp):
    from assistant import paths
    from assistant.ui.intro_view import IntroView, _HAVE_MULTIMEDIA

    if not _HAVE_MULTIMEDIA:
        pytest.skip("QtMultimedia недоступен в тестовом окружении")

    warp_path = paths.warp_video_path()
    if not warp_path.is_file():
        pytest.skip(f"Нет реального файла: {warp_path}")

    intro = IntroView(autostart=False)
    intro.resize(800, 600)
    intro.show()
    qapp.processEvents()
    _pump_events(qapp, 100)

    try:
        warp_layer = intro._get_layer("warp")
        if warp_layer is None:
            pytest.skip("Не удалось создать _MediaLayer для warp.mp4")

        started = warp_layer.start_play()
        if not started:
            pytest.skip("warp.mp4 существует, но player не запустил его")

        intro._visible_layer_key = "warp"
        intro._stack.setCurrentWidget(warp_layer.container)

        _pump_events(qapp, 200)
        warp_layer.sync_view()
        qapp.processEvents()
        _pump_events(qapp, 50)

        print("\n[VISIBLE WARP DIAGNOSTIC]")
        print("visible_layer_key =", intro._visible_layer_key)
        print("warp_layer_key    =", warp_layer)
        print("warp_visible      =", warp_layer.container.isVisible())
        print("warp_view_visible =", warp_layer.view.isVisible())
        print("intro_size        =", intro.size())
        print("intro_rect        =", intro.rect())
        print("container_rect    =", warp_layer.container.rect())
        print("view_rect         =", warp_layer.view.rect())
        print("viewport_rect     =", warp_layer.view.viewport().rect())
        print("view_geometry     =", warp_layer.view.geometry())
        print("container_geometry=", warp_layer.container.geometry())
        print("transform         =", warp_layer.view.transform())

        print("\n[ALL LAYERS]")
        for key, layer in intro._layers.items():
            if layer is None:
                continue
            try:
                print(
                    key,
                    "visible=", layer.container.isVisible(),
                    "view_visible=", layer.view.isVisible(),
                    "geometry=", layer.container.geometry(),
                    "view_geometry=", layer.view.geometry(),
                )
            except Exception as e:
                print(key, "error:", e)

        assert intro._visible_layer_key == "warp"
        assert warp_layer.container.isVisible()
        assert warp_layer.view.isVisible()

        intro_rect = intro.rect()
        container_rect = warp_layer.container.geometry()
        view_rect = warp_layer.view.geometry()

        assert container_rect.width() >= intro_rect.width() - 4
        assert container_rect.height() >= intro_rect.height() - 4
        assert view_rect.width() >= intro_rect.width() - 4
        assert view_rect.height() >= intro_rect.height() - 4
    finally:
        try:
            intro.stop()
        except Exception:
            pass
        try:
            intro.deleteLater()
        except Exception:
            pass
        qapp.processEvents()


# ---------------------------------------------------------------------------
# 6. Реальный MainWindow → SceneContainer → IntroView
# ---------------------------------------------------------------------------

def _find_intro_view(widget):
    from assistant.ui.intro_view import IntroView

    scene = getattr(widget, "scene", None)
    if scene is not None:
        intro = getattr(scene, "intro", None)
        if isinstance(intro, IntroView):
            return intro

    for child in widget.findChildren(IntroView):
        return child
    return None


def _find_scene_container(widget):
    from assistant.ui.scene_container import SceneContainer

    scene = getattr(widget, "scene", None)
    if isinstance(scene, SceneContainer):
        return scene
    for child in widget.findChildren(SceneContainer):
        return child
    return None


def test_real_production_hero_diagnostic(qapp):
    from assistant.events import EventBus
    from assistant.ui.main_window import MainWindow

    bus = EventBus()
    main_window = MainWindow(bus, settings_store=None)
    main_window.resize(800, 600)
    main_window.show()
    qapp.processEvents()
    _pump_events(qapp, 300)
    qapp.processEvents()

    try:
        intro = _find_intro_view(main_window)
        scene = _find_scene_container(main_window)

        if intro is None:
            pytest.skip("IntroView не найден в дереве MainWindow")
        if scene is None:
            pytest.skip("SceneContainer не найден в дереве MainWindow")

        warp_layer = None
        try:
            warp_layer = intro._get_layer("warp")
        except Exception as e:
            print(f"[HERO DIAG] warp _get_layer error: {e}")

        if warp_layer is not None:
            try:
                warp_layer.start_play()
            except Exception:
                pass
            try:
                intro._visible_layer_key = "warp"
                intro._stack.setCurrentWidget(warp_layer.container)
            except Exception:
                pass
            _pump_events(qapp, 200)
            try:
                warp_layer.sync_view()
            except Exception:
                pass
            qapp.processEvents()

        print("\n[REAL PRODUCTION HERO DIAGNOSTIC]")
        print("main_window.size     =", main_window.size())
        print("main_window.rect     =", main_window.rect())
        print("main_window.geometry =", main_window.geometry())

        print("scene.size           =", scene.size())
        print("scene.rect           =", scene.rect())
        print("scene.geometry       =", scene.geometry())
        try:
            print("scene.viewport.size  =", scene.viewport().size())
            print("scene.viewport.rect  =", scene.viewport().rect())
        except Exception:
            pass

        print("intro.size           =", intro.size())
        print("intro.rect           =", intro.rect())
        print("intro.geometry       =", intro.geometry())
        print("intro.isVisible      =", intro.isVisible())

        if warp_layer is not None:
            print("warp_visible         =",
                  warp_layer.container.isVisible())
            print("warp_view_visible    =",
                  warp_layer.view.isVisible())
            print("warp_container.geom  =",
                  warp_layer.container.geometry())
            print("warp_view.geom       =",
                  warp_layer.view.geometry())
            print("warp_view.viewport   =",
                  warp_layer.view.viewport().rect())

            try:
                native = warp_layer.item.nativeSize()
                print("warp_native_size     =",
                      (native.width(), native.height()))
                print("warp_transform       =",
                      warp_layer.view.transform())

                scene_rect = warp_layer.item.mapRectToScene(
                    warp_layer.item.boundingRect()
                )
                mapped = warp_layer.view.mapFromScene(
                    scene_rect
                ).boundingRect()
                print("warp_mapped_rect     =", mapped)
            except Exception as e:
                print("warp diagnostic error:", e)

        print("\n[PARENT CHAIN]")
        level = 0
        cur = intro
        while cur is not None:
            try:
                print(
                    level,
                    type(cur).__name__,
                    "visible=", cur.isVisible(),
                    "size=", cur.size(),
                    "geometry=", cur.geometry(),
                )
            except Exception as e:
                print(level, "error:", e)
            cur = cur.parentWidget()
            level += 1
            if level > 20:
                print("(too deep, abort)")
                break

        assert main_window.width() > 0
        assert main_window.height() > 0

        assert scene.width() > 0
        assert scene.height() > 0

        assert intro.isVisible()
        assert scene.isAncestorOf(intro)

        mw_w = main_window.width()
        intro_w = intro.width()
        assert intro_w >= mw_w - 40, (
            f"IntroView слишком узкий относительно MainWindow: "
            f"intro_w={intro_w}, main_window_w={mw_w}"
        )
    finally:
        try:
            main_window.close()
        except Exception:
            pass
        try:
            main_window.deleteLater()
        except Exception:
            pass
        qapp.processEvents()


# ---------------------------------------------------------------------------
# 7. Реальный preview → warp через production-механизм
# ---------------------------------------------------------------------------

def _dump_all_layers(intro, title: str) -> None:
    print(f"\n[{title}]")
    for key, layer in intro._layers.items():
        if layer is None:
            print(f"  {key}: None")
            continue
        try:
            print(
                f"  {key}: "
                f"visible={layer.container.isVisible()} "
                f"view_visible={layer.view.isVisible()} "
                f"geometry={layer.container.geometry()} "
                f"view_geometry={layer.view.geometry()}"
            )
        except Exception as e:
            print(f"  {key}: error {e}")


def test_real_preview_to_warp_transition(qapp):
    """
    Интеграционный тест реального перехода preview → warp
    через production-механизм IntroView._start() / EndOfMedia /
    _apply_state_to_view / _verify_pending_layer.

    Никакого ручного присваивания _visible_layer_key и
    _stack.setCurrentWidget. Никакого ручного start_play() для warp.

    Тест ждёт реального завершения preview.mp4 и проверяет, что
    production действительно переключил видимый слой на warp.
    """
    from assistant import paths
    from assistant.ui.intro_view import IntroView, _HAVE_MULTIMEDIA

    if not _HAVE_MULTIMEDIA:
        pytest.skip("QtMultimedia недоступен в тестовом окружении")

    preview_path = paths.preview_video_path()
    warp_path = paths.warp_video_path()

    if not preview_path.is_file():
        pytest.skip(f"Нет реального файла preview: {preview_path}")
    if not warp_path.is_file():
        pytest.skip(f"Нет реального файла warp: {warp_path}")

    intro = IntroView(autostart=False)
    intro.resize(800, 600)
    intro.show()
    qapp.processEvents()
    _pump_events(qapp, 100)

    try:
        # Запускаем production startup-механизм.
        intro._start()

        # Даём Qt инициализировать preview player и начать воспроизведение.
        _pump_events(qapp, 200)

        print("\n[REAL PREVIEW -> WARP DIAGNOSTIC]")

        # T0: старт.
        print("--- T0 (after _start) ---")
        print("preview_playing  =", intro._preview_playing)
        print("visible_layer_key=", intro._visible_layer_key)
        print("pending_layer_key=", intro._pending_layer_key)
        print("pending_prev_key =", intro._pending_prev_key)

        preview_layer = intro._layers.get("preview")
        if preview_layer is not None:
            print("preview container visible =",
                  preview_layer.container.isVisible())
            print("preview view visible      =",
                  preview_layer.view.isVisible())
            print("preview geometry          =",
                  preview_layer.container.geometry())
            print("preview view geometry     =",
                  preview_layer.view.geometry())
            try:
                pn = preview_layer.item.nativeSize()
                print("preview native size       =",
                      (pn.width(), pn.height()))
                print("preview transform         =",
                      preview_layer.view.transform())
            except Exception as e:
                print("preview diagnostic error:", e)

        # Отслеживаем моменты, когда происходит смена состояния
        # preview_playing и pending/visible keys.
        seen_preview_end = {"v": False}
        seen_pending_warp = {"v": False}

        def _on_preview_end():
            if (not seen_preview_end["v"]
                    and intro._preview_playing is False):
                seen_preview_end["v"] = True
                print("--- T1 (preview ended) ---")
                print("preview_playing  =", intro._preview_playing)
                print("visible_layer_key=", intro._visible_layer_key)
                print("pending_layer_key=", intro._pending_layer_key)
                print("pending_prev_key =", intro._pending_prev_key)

        def _on_pending_warp():
            if (not seen_pending_warp["v"]
                    and intro._pending_layer_key == "warp"):
                seen_pending_warp["v"] = True
                print("--- T2 (pending=warp) ---")
                print("preview_playing  =", intro._preview_playing)
                print("visible_layer_key=", intro._visible_layer_key)
                print("pending_layer_key=", intro._pending_layer_key)
                print("pending_prev_key =", intro._pending_prev_key)

        # Ждём перехода visible_layer_key == "warp", наблюдая за
        # промежуточными точками.
        deadline = time.monotonic() + 20.0
        while time.monotonic() < deadline:
            qapp.processEvents()
            _on_preview_end()
            _on_pending_warp()
            if intro._visible_layer_key == "warp":
                break
            _pump_events(qapp, 50)

        # T3: финальное состояние.
        print("--- T3 (after transition) ---")
        print("preview_playing  =", intro._preview_playing)
        print("visible_layer_key=", intro._visible_layer_key)
        print("pending_layer_key=", intro._pending_layer_key)
        print("pending_prev_key =", intro._pending_prev_key)

        print("intro.size        =", intro.size())
        print("intro.geometry    =", intro.geometry())

        warp_layer = intro._layers.get("warp")

        if warp_layer is not None:
            print("warp.container.visible =",
                  warp_layer.container.isVisible())
            print("warp.container.geometry=",
                  warp_layer.container.geometry())
            print("warp.view.visible      =",
                  warp_layer.view.isVisible())
            print("warp.view.geometry     =",
                  warp_layer.view.geometry())
            print("warp.viewport.rect     =",
                  warp_layer.view.viewport().rect())

            try:
                native = warp_layer.item.nativeSize()
                print("warp.native_size       =",
                      (native.width(), native.height()))
                print("warp.transform         =",
                      warp_layer.view.transform())

                scene_rect = warp_layer.item.mapRectToScene(
                    warp_layer.item.boundingRect()
                )
                mapped = warp_layer.view.mapFromScene(
                    scene_rect
                ).boundingRect()
                print("warp.mapped_rect       =", mapped)
            except Exception as e:
                print("warp diagnostic error:", e)

        _dump_all_layers(intro, "LAYERS AFTER PREVIEW")

        # Проверяем, что production действительно переключил на warp.
        assert intro._visible_layer_key == "warp", (
            f"После preview видимый слой не warp, а "
            f"{intro._visible_layer_key!r}. См. T0..T3 в выводе."
        )

        if warp_layer is not None:
            assert warp_layer.container.isVisible(), (
                "warp.container не видим после preview → warp"
            )
            assert warp_layer.view.isVisible(), (
                "warp.view не видим после preview → warp"
            )

            intro_rect = intro.rect()
            cg = warp_layer.container.geometry()
            vg = warp_layer.view.geometry()
            assert cg.width() >= intro_rect.width() - 4, (
                f"warp.container узкий: {cg}, intro_rect={intro_rect}"
            )
            assert cg.height() >= intro_rect.height() - 4, (
                f"warp.container низкий: {cg}, intro_rect={intro_rect}"
            )
            assert vg.width() >= intro_rect.width() - 4, (
                f"warp.view узкий: {vg}, intro_rect={intro_rect}"
            )
            assert vg.height() >= intro_rect.height() - 4, (
                f"warp.view низкий: {vg}, intro_rect={intro_rect}"
            )
    finally:
        try:
            intro.stop()
        except Exception:
            pass
        try:
            intro.deleteLater()
        except Exception:
            pass
        qapp.processEvents()


def run_all():
    print("pytest -v tools/test_intro_view.py", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(run_all())
