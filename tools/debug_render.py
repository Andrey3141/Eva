"""
Изолированная проверка компонентов UI, которые могут давать визуальный
скачок/мигание: видео-интро, GIF-интро, GIF-аватар, целиком IntroView,
целиком SceneContainer.

Запуск:
    python -m tools.debug_render --target=video
    python -m tools.debug_render --target=gif
    python -m tools.debug_render --target=avatar
    python -m tools.debug_render --target=intro
    python -m tools.debug_render --target=scene
"""
from __future__ import annotations

import argparse
import os
import sys

from PySide6.QtCore import Qt, QTimer, QElapsedTimer, QUrl
from PySide6.QtGui import QMovie
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QWidget, QVBoxLayout

from assistant import paths


def _log(msg: str) -> None:
    print(f"[DEBUG] {msg}", flush=True)


# ---------------------------------------------------------------------------
# Режимы
# ---------------------------------------------------------------------------

def run_video() -> int:
    try:
        from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
        from PySide6.QtMultimediaWidgets import QGraphicsVideoItem
        from PySide6.QtWidgets import QGraphicsScene, QGraphicsView
    except Exception as e:
        _log(f"QtMultimedia недоступен: {e}")
        return 2

    video = paths.preview_video_path()
    _log(f"video: {video}")
    if not video.is_file():
        _log("нет файла preview.mp4")
        return 2

    app = QApplication.instance() or QApplication(sys.argv)
    win = QMainWindow()
    win.resize(1280, 720)
    win.setWindowTitle("debug: video")

    scene = QGraphicsScene()
    view = QGraphicsView(scene)
    item = QGraphicsVideoItem()
    scene.addItem(item)
    win.setCentralWidget(view)

    player = QMediaPlayer()
    audio = QAudioOutput()
    audio.setVolume(0.0)
    player.setAudioOutput(audio)
    player.setVideoOutput(item)
    player.setSource(QUrl.fromLocalFile(str(video)))

    timers = {"start": QElapsedTimer()}

    def on_status(status):
        _log(f"status={status}")

    def on_native_size(sz):
        _log(f"nativeSize={sz}")
        scene.setSceneRect(item.boundingRect())
        view.fitInView(item, Qt.AspectRatioMode.KeepAspectRatio)
        view.centerOn(item)

    def on_started():
        timers["start"].start()
        _log("player.started")

    def on_end():
        _log(f"player.EndOfMedia elapsed={timers['start'].elapsed()}ms")
        QTimer.singleShot(500, app.quit)

    player.mediaStatusChanged.connect(on_status)
    item.nativeSizeChanged.connect(on_native_size)
    player.mediaStatusChanged.connect(
        lambda s: on_started() if s == QMediaPlayer.MediaStatus.LoadingMedia else None
    )
    player.mediaStatusChanged.connect(
        lambda s: on_end() if s == QMediaPlayer.MediaStatus.EndOfMedia else None
    )

    win.show()
    player.play()
    return app.exec()


def run_gif() -> int:
    gif = paths.warp_gif_path()
    _log(f"gif: {gif}")
    if not gif.is_file():
        _log("нет файла warp.gif")
        return 2

    app = QApplication.instance() or QApplication(sys.argv)
    win = QMainWindow()
    win.resize(640, 480)
    win.setWindowTitle("debug: gif")

    label = QLabel()
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    movie = QMovie(str(gif))
    movie.setCacheMode(QMovie.CacheMode.CacheAll)
    label.setMovie(movie)
    win.setCentralWidget(label)

    state = {"prev": -1, "t": QElapsedTimer()}

    def on_frame(idx):
        n = movie.frameCount()
        if state["prev"] == -1:
            state["t"].start()
        dt = state["t"].restart()
        marker = ""
        if state["prev"] == n - 1 and idx == 0:
            marker = " <== LOOP"
        if marker or dt > 100:
            _log(f"frame {state['prev']} -> {idx} of {n} dt={dt}ms{marker}")
        state["prev"] = idx

    def on_state(s):
        _log(f"state={s}")

    movie.frameChanged.connect(on_frame)
    movie.stateChanged.connect(on_state)

    win.show()
    movie.start()
    return app.exec()


def run_avatar() -> int:
    from assistant.ui.avatar.gif_renderer import GifRenderer

    gif = paths.warp_gif_path()
    _log(f"avatar gif: {gif}")
    if not gif.is_file():
        _log("нет файла warp.gif")
        return 2

    app = QApplication.instance() or QApplication(sys.argv)
    win = QMainWindow()
    win.resize(480, 480)
    win.setWindowTitle("debug: avatar")

    renderer = GifRenderer(gif)
    win.setCentralWidget(renderer.widget())

    state = {"prev": -1, "t": QElapsedTimer()}

    def on_frame(idx):
        n = renderer._movie.frameCount()
        if state["prev"] == -1:
            state["t"].start()
        dt = state["t"].restart()
        marker = ""
        if state["prev"] == n - 1 and idx == 0:
            marker = " <== LOOP"
        if marker or dt > 100:
            _log(f"frame {state['prev']} -> {idx} of {n} dt={dt}ms{marker}")
        state["prev"] = idx

    renderer._movie.frameChanged.connect(on_frame)

    win.show()
    renderer.start()
    return app.exec()


def run_intro() -> int:
    from assistant.ui.intro_view import IntroView

    _log("IntroView standalone")
    app = QApplication.instance() or QApplication(sys.argv)
    win = QMainWindow()
    win.resize(1280, 720)
    win.setWindowTitle("debug: intro")

    intro = IntroView(autostart=True)
    win.setCentralWidget(intro)

    win.show()
    return app.exec()


def run_scene() -> int:
    from assistant.ui.scene_container import SceneContainer

    _log("SceneContainer standalone (пустая UI-секция)")
    app = QApplication.instance() or QApplication(sys.argv)
    win = QMainWindow()
    win.resize(1280, 720)
    win.setWindowTitle("debug: scene")

    ui_section = QWidget()
    lay = QVBoxLayout(ui_section)
    lay.addWidget(QLabel("UI section placeholder"))

    scene = SceneContainer(ui_section=ui_section)
    win.setCentralWidget(scene)

    orig_sync = scene._sync_section_heights

    def logged_sync():
        h = scene.viewport().height()
        _log(f"_sync_section_heights h={h} s0={scene._s0.height()} "
             f"s1={scene._s1.height()}")
        return orig_sync()

    scene._sync_section_heights = logged_sync  # type: ignore[method-assign]

    win.show()
    return app.exec()


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

_TARGETS = {
    "video": run_video,
    "gif": run_gif,
    "avatar": run_avatar,
    "intro": run_intro,
    "scene": run_scene,
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--target",
        choices=sorted(_TARGETS.keys()),
        required=True,
        help="что проверяем",
    )
    args = parser.parse_args()

    if not os.path.exists("assistant"):
        _log("запускать из корня проекта")
        return 2

    return _TARGETS[args.target]()


if __name__ == "__main__":
    sys.exit(main())
