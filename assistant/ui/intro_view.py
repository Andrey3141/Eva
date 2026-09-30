"""
IntroView — первая (Hero) секция страницы.

Модель поведения:
  START:
      preview.mp4 → один раз → переход на актуальное состояние.
      preview не прерывается изменением состояния; новое состояние
      запоминается и применяется после окончания preview.

  Обычные состояния (IDLE / LISTENING / WAITING_CONFIRMATION / ERROR):
      warp.mp4 → loop.

  SPEAKING:
      speaks.mp4 → loop, если файл существует и Qt его открыл.

  THINKING:
      thinks.mp4 → loop, если файл существует и Qt его открыл.

  Отсутствие warp.mp4:
      после preview оставляем preview на экране.
      При SPEAKING/THINKING пытаемся переключиться на speaks/thinks.

Безопасное переключение:
      1. Определить целевой слой.
      2. Если файла нет или слой не готов — ничего не делать.
      3. Запустить новый слой (start_play()).
      4. НЕ трогать видимый слой и НЕ останавливать старый.
      5. Через короткое окно проверить статус нового слоя.
         OK → новый становится видимым, старый pause().
         FAIL → ничего не менять, старый продолжает играть.
         WAIT → перепроверить ещё раз до MAX_WAIT_MS.

      После setCurrentWidget(pending_layer.container) планируется
      отложенный sync_view — QGraphicsView получает реальный размер
      viewport только после показа виджета, поэтому transform нужно
      пересчитать в следующем цикле event loop.

Масштабирование:
      sync_view использует KeepAspectRatioByExpanding:
        - видео заполняет 100% viewport;
        - пропорции сохраняются;
        - при несовпадении AR кадр обрезается по краям (crop);
        - crop строго центрирован.

Публичный контракт:
  IntroView(), IntroView(autostart=False), stop(), showEvent,
  resizeEvent, set_state(state).
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QUrl, QSizeF, QRectF, QTimer
from PySide6.QtGui import QPalette, QColor, QBrush
from PySide6.QtWidgets import (
    QFrame, QSizePolicy, QStackedLayout, QVBoxLayout, QWidget,
)

from assistant import paths

try:
    from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
    from PySide6.QtMultimediaWidgets import QGraphicsVideoItem
    from PySide6.QtWidgets import QGraphicsScene, QGraphicsView
    _HAVE_MULTIMEDIA = True
except Exception:
    QMediaPlayer = None
    QAudioOutput = None
    QGraphicsVideoItem = None
    QGraphicsScene = None
    QGraphicsView = None
    _HAVE_MULTIMEDIA = False


_WHITE = "#ffffff"

ROLLBACK_DELAY_MS = 200
MAX_WAIT_MS = 2000

_STATE_TO_MEDIA = {
    "speaking": "speaks",
    "thinking": "thinks",
}


def _status_name(status) -> str:
    if status is None:
        return "NoMedia"
    name = getattr(status, "name", None)
    if name:
        return str(name)
    try:
        if QMediaPlayer is not None:
            m = QMediaPlayer.MediaStatus
            for nm in ("NoMedia", "LoadingMedia", "LoadedMedia",
                       "BufferingMedia", "BufferedMedia",
                       "EndOfMedia", "InvalidMedia", "StalledMedia"):
                if hasattr(m, nm) and status == getattr(m, nm):
                    return nm
    except Exception:
        pass
    return "Unknown"


class _MediaLayer:
    """
    Один видео-слой: контейнер + QGraphicsView + QGraphicsVideoItem + player.
    """

    def __init__(self, parent_widget: QWidget, video_path, loop: bool):
        self.video_path = video_path
        self.loop = bool(loop)
        self.container = QWidget(parent_widget)
        self.container.setStyleSheet(f"background: {_WHITE};")
        self.container.setSizePolicy(QSizePolicy.Policy.Expanding,
                                     QSizePolicy.Policy.Expanding)
        self.container.setAutoFillBackground(True)
        pal = self.container.palette()
        pal.setColor(QPalette.ColorRole.Window, QColor(_WHITE))
        self.container.setPalette(pal)

        self.layout = QVBoxLayout(self.container)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        self.view = None
        self.item = None
        self.player = None
        self.audio = None
        self.scene = None
        self._error_seen: str = ""

        self._build()

    # ------------------------------------------------------------------
    def _build(self) -> None:
        if not _HAVE_MULTIMEDIA:
            return
        if self.video_path is None or not self.video_path.is_file():
            return

        self.player = QMediaPlayer()
        self.audio = QAudioOutput()
        self.audio.setVolume(0.0)
        self.player.setAudioOutput(self.audio)

        try:
            self.player.errorOccurred.connect(self._on_error_occurred)
        except Exception:
            try:
                self.player.error.connect(self._on_error_occurred)
            except Exception:
                pass

        self.scene = QGraphicsScene()
        self.scene.setBackgroundBrush(QBrush(QColor(_WHITE)))
        self.scene.setSceneRect(QRectF(0, 0, 1, 1))

        self.view = QGraphicsView(self.scene)
        self.view.setStyleSheet(
            f"QGraphicsView {{ background: {_WHITE}; border: none; }}"
        )
        self.view.setFrameShape(QFrame.Shape.NoFrame)
        self.view.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.view.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.view.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.view.setSizePolicy(QSizePolicy.Policy.Expanding,
                                QSizePolicy.Policy.Expanding)
        self.view.setAutoFillBackground(True)
        vpal = self.view.palette()
        vpal.setColor(QPalette.ColorRole.Window, QColor(_WHITE))
        vpal.setColor(QPalette.ColorRole.Base, QColor(_WHITE))
        self.view.setPalette(vpal)

        self.item = QGraphicsVideoItem()
        self.scene.addItem(self.item)
        self.player.setVideoOutput(self.item)

        self.item.nativeSizeChanged.connect(self._on_native_size)

        self.player.setSource(QUrl.fromLocalFile(str(self.video_path)))

        if self.loop:
            try:
                self.player.setLoops(QMediaPlayer.Loops.Infinite)
            except Exception:
                pass

        self.layout.addWidget(self.view, 1)

    # ------------------------------------------------------------------
    def _on_error_occurred(self, *_args) -> None:
        msg = ""
        if len(_args) >= 2:
            msg = str(_args[1])
        elif len(_args) == 1:
            msg = str(_args[0])
        self._error_seen = msg or "media error"
        print(
            f"[INTRO] media error for {self.video_path.name}: {msg}",
            flush=True,
        )

    @property
    def is_ready(self) -> bool:
        if self.player is None:
            return False
        if self._error_seen:
            return False
        try:
            status_name = _status_name(self.player.mediaStatus())
        except Exception:
            return False
        if status_name in ("InvalidMedia", "NoMedia"):
            return False
        return True

    def _on_native_size(self, _sz) -> None:
        self.sync_view()

    # ------------------------------------------------------------------
    def sync_view(self) -> None:
        """
        Вписывает видео в QGraphicsView.

        Стратегия — KeepAspectRatioByExpanding:
          - видео заполняет 100% viewport;
          - пропорции сохраняются;
          - при несовпадении AR кадр обрезается по краям (crop);
          - crop строго центрирован: view.sceneRect рассчитывается
            так, чтобы центр item совпал с центром viewport.
        """
        if self.view is None or self.item is None or self.scene is None:
            return
        try:
            viewport = self.view.viewport()
            vw = viewport.width()
            vh = viewport.height()
            if vw <= 0 or vh <= 0:
                return
            src = self.item.nativeSize()
            sw = src.width()
            sh = src.height()
            if sw <= 0 or sh <= 0:
                self.scene.setSceneRect(QRectF(0, 0, vw, vh))
                return

            self.item.setSize(QSizeF(sw, sh))
            self.item.setPos(0, 0)
            scene_rect = self.item.mapRectToScene(self.item.boundingRect())
            self.scene.setSceneRect(scene_rect)

            self.view.fitInView(
                scene_rect,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            )

            t = self.view.transform()
            m11 = t.m11()
            m22 = t.m22()
            if m11 > 0 and m22 > 0:
                vp_w_scene = vw / m11
                vp_h_scene = vh / m22
            else:
                vp_w_scene = float(vw)
                vp_h_scene = float(vh)
            cx = scene_rect.center().x()
            cy = scene_rect.center().y()
            centered = QRectF(
                cx - vp_w_scene / 2.0,
                cy - vp_h_scene / 2.0,
                vp_w_scene,
                vp_h_scene,
            )
            self.view.setSceneRect(centered)

            self.view.horizontalScrollBar().setValue(0)
            self.view.verticalScrollBar().setValue(0)
        except RuntimeError:
            return

    def start_play(self) -> bool:
        if self.player is None:
            return False
        if self._error_seen:
            print(
                f"[INTRO] cannot start {self.video_path.name}: "
                f"previous error={self._error_seen!r}",
                flush=True,
            )
            return False
        status_name = _status_name(self.player.mediaStatus())
        if status_name in ("InvalidMedia", "NoMedia"):
            print(
                f"[INTRO] cannot start {self.video_path.name}: "
                f"status={status_name}",
                flush=True,
            )
            return False
        try:
            self.player.play()
        except Exception as e:
            print(
                f"[INTRO] play() raised for {self.video_path.name}: {e}",
                flush=True,
            )
            return False
        return True

    def check_after_play(self) -> str:
        if self.player is None:
            return "fail"
        if self._error_seen:
            return "fail"
        try:
            status_name = _status_name(self.player.mediaStatus())
        except Exception:
            return "fail"

        if status_name in ("InvalidMedia", "NoMedia"):
            return "fail"
        if status_name in ("LoadedMedia", "BufferedMedia",
                           "BufferingMedia", "StalledMedia",
                           "EndOfMedia"):
            return "ok"
        if status_name in ("LoadingMedia", "Unknown"):
            return "wait"
        return "fail"

    def pause(self) -> None:
        if self.player is None:
            return
        try:
            self.player.pause()
        except Exception:
            pass

    def stop(self) -> None:
        if self.player is None:
            return
        try:
            self.player.stop()
        except Exception:
            pass


class IntroView(QFrame):
    def __init__(self, parent: QWidget | None = None, autostart: bool = True):
        super().__init__(parent)
        self._autostart = bool(autostart)

        self.setObjectName("introView")
        self.setStyleSheet(f"QFrame#introView {{ background: {_WHITE}; }}")
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Expanding)

        pal = self.palette()
        pal.setColor(QPalette.ColorRole.Window, QColor(_WHITE))
        self.setAutoFillBackground(True)
        self.setPalette(pal)

        self._preview_path = paths.preview_video_path()
        self._warp_path = paths.warp_video_path()
        self._speaks_path = paths.speaks_video_path()
        self._thinks_path = paths.thinks_video_path()

        self._current_state: str = "idle"
        self._preview_playing = False
        self._visible_layer_key: str | None = None

        self._pending_layer_key: str | None = None
        self._pending_prev_key: str | None = None
        self._pending_waited_ms: int = 0

        self._stack = QStackedLayout(self)
        self._stack.setContentsMargins(0, 0, 0, 0)
        self._stack.setSpacing(0)
        self._stack.setStackingMode(QStackedLayout.StackingMode.StackOne)

        self._fallback = self._build_fallback_layer()
        self._stack.addWidget(self._fallback)
        self._stack.setCurrentWidget(self._fallback)

        self._layers: dict[str, _MediaLayer] = {}

        if self._autostart:
            QTimer.singleShot(0, self._start)

    # ------------------------------------------------------------------
    def _build_fallback_layer(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet(f"background: {_WHITE};")
        w.setSizePolicy(QSizePolicy.Policy.Expanding,
                        QSizePolicy.Policy.Expanding)
        w.setAutoFillBackground(True)
        pal = w.palette()
        pal.setColor(QPalette.ColorRole.Window, QColor(_WHITE))
        w.setPalette(pal)
        return w

    def _get_layer(self, key: str) -> _MediaLayer | None:
        if key in self._layers:
            return self._layers[key]

        if key == "preview":
            path = self._preview_path
            loop = False
        elif key == "warp":
            path = self._warp_path
            loop = True
        elif key == "speaks":
            path = self._speaks_path
            loop = True
        elif key == "thinks":
            path = self._thinks_path
            loop = True
        else:
            return None

        layer = _MediaLayer(self, path, loop=loop)
        if not layer.is_ready:
            return None
        self._stack.addWidget(layer.container)
        self._layers[key] = layer
        return layer

    # ------------------------------------------------------------------
    def _start(self) -> None:
        preview = self._get_layer("preview")
        if preview is not None:
            self._preview_playing = True
            self._visible_layer_key = "preview"
            self._stack.setCurrentWidget(preview.container)
            try:
                preview.player.mediaStatusChanged.connect(
                    self._on_preview_status
                )
            except Exception:
                pass
            if preview.start_play():
                return
            self._preview_playing = False

        self._apply_state_to_view()

    def _on_preview_status(self, status) -> None:
        if not _HAVE_MULTIMEDIA:
            return
        name = _status_name(status)
        if name in ("EndOfMedia", "InvalidMedia", "NoMedia"):
            self._preview_playing = False
            self._apply_state_to_view()

    # ------------------------------------------------------------------
    def set_state(self, state) -> None:
        try:
            value = getattr(state, "value", None) or str(state)
            self._current_state = str(value).lower()
        except Exception:
            self._current_state = "idle"

        if self._preview_playing:
            return
        self._apply_state_to_view()

    def _target_layer_key(self) -> str:
        media_kind = _STATE_TO_MEDIA.get(self._current_state)
        if media_kind == "speaks":
            return "speaks"
        if media_kind == "thinks":
            return "thinks"
        return "warp"

    def _apply_state_to_view(self) -> None:
        if self._preview_playing:
            return
        if self._pending_layer_key is not None:
            return

        target_key = self._target_layer_key()

        if target_key == self._visible_layer_key:
            return

        target_layer = self._get_layer(target_key)
        if target_layer is None:
            return

        if not target_layer.is_ready:
            print(
                f"[INTRO] target layer {target_key!r} is not ready; "
                f"keeping current layer {self._visible_layer_key!r}",
                flush=True,
            )
            return

        prev_key = self._visible_layer_key

        started = target_layer.start_play()
        if not started:
            print(
                f"[INTRO] failed to start layer {target_key!r}; "
                f"keeping current layer {prev_key!r}",
                flush=True,
            )
            return

        self._pending_layer_key = target_key
        self._pending_prev_key = prev_key
        self._pending_waited_ms = 0
        QTimer.singleShot(ROLLBACK_DELAY_MS, self._verify_pending_layer)

    def _verify_pending_layer(self) -> None:
        pending_key = self._pending_layer_key
        if pending_key is None:
            return
        pending_layer = self._layers.get(pending_key)
        if pending_layer is None:
            self._pending_layer_key = None
            self._pending_prev_key = None
            self._pending_waited_ms = 0
            return

        result = pending_layer.check_after_play()

        if result == "wait":
            self._pending_waited_ms += ROLLBACK_DELAY_MS
            if self._pending_waited_ms >= MAX_WAIT_MS:
                print(
                    f"[INTRO] layer {pending_key!r} never confirmed; "
                    f"keeping current layer {self._pending_prev_key!r}",
                    flush=True,
                )
                self._pending_layer_key = None
                self._pending_prev_key = None
                self._pending_waited_ms = 0
                return
            QTimer.singleShot(ROLLBACK_DELAY_MS, self._verify_pending_layer)
            return

        if result == "fail":
            print(
                f"[INTRO] layer {pending_key!r} failed to play; "
                f"keeping current layer {self._pending_prev_key!r}",
                flush=True,
            )
            self._pending_layer_key = None
            self._pending_prev_key = None
            self._pending_waited_ms = 0
            return

        # result == "ok"
        prev_key = self._pending_prev_key
        self._pending_layer_key = None
        self._pending_prev_key = None
        self._pending_waited_ms = 0

        self._visible_layer_key = pending_key
        self._stack.setCurrentWidget(pending_layer.container)

        # После setCurrentWidget QGraphicsView получает реальный размер
        # viewport только в следующем цикле event loop (layout ещё
        # не применился). Планируем sync_view отложенно, чтобы
        # transform был рассчитан под актуальный viewport, а не под
        # дефолтный 640×480.
        QTimer.singleShot(0, pending_layer.sync_view)

        if prev_key and prev_key in self._layers and prev_key != pending_key:
            try:
                self._layers[prev_key].pause()
            except Exception:
                pass

    # ------------------------------------------------------------------
    def resizeEvent(self, event):
        super().resizeEvent(event)
        for layer in list(self._layers.values()):
            QTimer.singleShot(0, layer.sync_view)

    def showEvent(self, event):
        super().showEvent(event)
        for layer in list(self._layers.values()):
            QTimer.singleShot(0, layer.sync_view)

    # ------------------------------------------------------------------
    def stop(self) -> None:
        for layer in list(self._layers.values()):
            layer.stop()
