from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QMovie
from PySide6.QtWidgets import QLabel, QSizePolicy, QWidget

from .base import AvatarRenderer


class GifRenderer(AvatarRenderer):
    """
    GIF-анимация через QMovie с аппаратным/ОЗУ-кэшированием кадров,
    фиксацией размера и корректным перезапуском цикла.
    """

    def __init__(self, file_path: Path):
        super().__init__(file_path)
        self._label = QLabel()
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setStyleSheet("background: transparent;")

        # Фиксируем размер QLabel и включаем масштабирование содержимого
        self._label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._label.setFixedSize(240, 240)
        self._label.setScaledContents(True)

        self._movie = QMovie(str(self.file_path))
        self._movie.setScaledSize(QSize(240, 240))
        
        # Кэшируем кадры в ОЗУ, чтобы не декодировать с диска на каждом круге
        self._movie.setCacheMode(QMovie.CacheMode.CacheAll)

        # Перезапуск цикла по сигналу завершения проигрывания (вместо setLoopCount)
        self._movie.finished.connect(self._on_finished)

        self._label.setMovie(self._movie)

    def _on_finished(self) -> None:
        """Если GIF проигрался до конца и остановился — отматываем на 0 кадр и стартуем заново."""
        if self._movie.isValid():
            self._movie.jumpToFrame(0)
            self._movie.start()

    def widget(self) -> QWidget:
        return self._label

    def start(self) -> None:
        if self._movie.isValid():
            if self._movie.state() == QMovie.MovieState.NotRunning:
                self._movie.jumpToFrame(0)
                self._movie.start()

    def stop(self) -> None:
        if self._movie.isValid():
            self._movie.stop()

    def dispose(self) -> None:
        try:
            self._movie.stop()
        except Exception:
            pass
