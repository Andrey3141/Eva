from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from .base import AvatarRenderer


class VideoRenderer(AvatarRenderer):
    """
    Короткое видео через QMediaPlayer + QVideoWidget.
    Если QtMultimedia недоступен — работает как placeholder (label).
    """

    def __init__(self, file_path: Path):
        super().__init__(file_path)
        self._container = QWidget()
        layout = QVBoxLayout(self._container)
        layout.setContentsMargins(0, 0, 0, 0)

        try:
            from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
            from PySide6.QtMultimediaWidgets import QVideoWidget

            self._player = QMediaPlayer()
            self._audio = QAudioOutput()
            self._audio.setVolume(0.0)  # звук видео нам не нужен — это аватар
            self._player.setAudioOutput(self._audio)

            self._video_widget = QVideoWidget()
            self._video_widget.setFixedSize(240, 240)
            self._player.setVideoOutput(self._video_widget)

            self._player.setSource(QUrl.fromLocalFile(str(self.file_path)))
            self._player.setLoops(QMediaPlayer.Loops.Infinite)

            layout.addWidget(self._video_widget)
        except Exception:
            self._player = None
            fallback = QLabel(f"[video: {self.file_path.name}]")
            fallback.setAlignment(fallback.alignment())
            layout.addWidget(fallback)

    def widget(self) -> QWidget:
        return self._container

    def start(self) -> None:
        if self._player is not None:
            self._player.play()

    def stop(self) -> None:
        if self._player is not None:
            self._player.pause()

    def dispose(self) -> None:
        if self._player is not None:
            try:
                self._player.stop()
            except Exception:
                pass
