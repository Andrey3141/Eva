from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QLabel, QWidget

from .base import AvatarRenderer


class ImageRenderer(AvatarRenderer):
    """Статичная картинка (PNG/JPG)."""

    def __init__(self, file_path: Path):
        super().__init__(file_path)
        self._label = QLabel()
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setStyleSheet("background: transparent;")
        self._pixmap = QPixmap(str(self.file_path)) if self.file_path.exists() else QPixmap()
        self._rescale()

    def widget(self) -> QWidget:
        return self._label

    def _rescale(self) -> None:
        if self._pixmap.isNull():
            self._label.setText("")
            return
        self._label.setPixmap(
            self._pixmap.scaled(
                240, 240,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
