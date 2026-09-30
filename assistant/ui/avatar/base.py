from abc import ABC, abstractmethod
from pathlib import Path

from PySide6.QtWidgets import QWidget


class AvatarRenderer(ABC):
    """
    Абстракция рендера аватара.
    Ничего не знает о состояниях — только о конкретном файле.
    Переключение состояний делает AvatarView.
    """

    def __init__(self, file_path: Path):
        self.file_path = Path(file_path)

    @abstractmethod
    def widget(self) -> QWidget:
        """Возвращает QWidget, который будет вставлен в AvatarView."""

    def start(self) -> None:
        """Запуск анимации (если есть). По умолчанию — no-op."""

    def stop(self) -> None:
        """Остановка анимации. По умолчанию — no-op."""

    def dispose(self) -> None:
        """Освобождение ресурсов перед заменой. По умолчанию — no-op."""
