"""
Изолированная диагностика геометрии QGraphicsVideoItem внутри IntroView.

Использует host + QVBoxLayout + show(), чтобы QGraphicsView реально
получил размер от layout (а не остался в дефолтных 640x480).

Правильное преобразование item → scene → view:
    scene_rect = item.mapRectToScene(item.boundingRect())
    mapped = view.mapFromScene(scene_rect).boundingRect()

Запуск:
    python -m tools.debug_video_geometry
"""
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout
from PySide6.QtCore import QSizeF


def _print_state(tag: str, v):
    view = v._video_view
    item = v._video_item
    scene = v._video_scene
    if view is None or item is None or scene is None:
        print(f"[{tag}] view/item/scene не созданы", flush=True)
        return

    scene_rect = item.mapRectToScene(item.boundingRect())
    mapped = view.mapFromScene(scene_rect).boundingRect()

    t = view.transform()
    print(
        f"[{tag}]",
        "view.size=", view.size(),
        "viewport.size=", view.viewport().size(),
        "view.rect=", view.rect(),
        "viewport.rect=", view.viewport().rect(),
        "sceneRect=", scene.sceneRect(),
        "item.size=", item.size(),
        "item.pos=", item.pos(),
        "item.scene_rect=", scene_rect,
        "m11=", t.m11(), "m22=", t.m22(),
        "mapped=", mapped,
        "hscroll=", view.horizontalScrollBar().value(),
        "vscroll=", view.verticalScrollBar().value(),
        flush=True,
    )


def main() -> int:
    try:
        from PySide6.QtMultimedia import QMediaPlayer  # noqa: F401
    except Exception:
        print("QtMultimedia недоступен — диагностика невозможна", flush=True)
        return 2

    from assistant.ui import intro_view as intro_mod
    if not intro_mod._HAVE_MULTIMEDIA:
        print("IntroView._HAVE_MULTIMEDIA = False — диагностика невозможна", flush=True)
        return 2

    app = QApplication.instance() or QApplication(sys.argv)

    host = QWidget()
    layout = QVBoxLayout(host)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)

    v = intro_mod.IntroView(autostart=True)
    layout.addWidget(v)

    if v._video_item is None or v._video_view is None:
        print("QGraphicsVideoItem не создан", flush=True)
        return 2

    fake = QSizeF(990, 1280)
    v._video_item.nativeSize = lambda: fake  # type: ignore[method-assign]

    print("=== A. Какая координата является viewport ===", flush=True)
    host.resize(1920, 1080)
    host.show()
    app.processEvents()
    v._sync_video_view()
    app.processEvents()
    _print_state("A.after_sync_1920x1080", v)

    print()
    print("=== B. Что происходит с transform после resize ===", flush=True)

    for w, h in ((1920, 1080), (1080, 1920), (640, 480)):
        host.resize(w, h)
        app.processEvents()
        v._sync_video_view()
        app.processEvents()
        _print_state(f"B.after_{w}x{h}", v)

    try:
        v.stop()
    except Exception:
        pass
    v.deleteLater()
    host.deleteLater()
    return 0


if __name__ == "__main__":
    sys.exit(main())
