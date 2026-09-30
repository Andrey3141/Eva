"""
AvatarRegistry — сопоставление состояния и файла аватара.

Модель:
  IDLE / LISTENING / WAITING_CONFIRMATION / ERROR → warp.mp4
  SPEAKING                                        → speaks.mp4
  THINKING                                        → thinks.mp4

Правило: если для состояния задан явный файл в state_map и его нет —
file_for_state() возвращает None (не fallback на warp).
Если для состояния нет записи в state_map — используется
base_filename (warp.mp4) при условии, что он существует.
"""
from __future__ import annotations

import os
from pathlib import Path

from .base import AvatarRenderer
from .gif_renderer import GifRenderer
from .image_renderer import ImageRenderer
from .video_renderer import VideoRenderer


_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
_GIF_EXT = {".gif"}
_VIDEO_EXT = {".mp4", ".webm", ".mkv", ".mov"}


def build_renderer_for(file_path: Path) -> AvatarRenderer | None:
    if not file_path.exists() or not file_path.is_file():
        return None

    ext = file_path.suffix.lower()
    if ext in _GIF_EXT:
        return GifRenderer(file_path)
    if ext in _VIDEO_EXT:
        return VideoRenderer(file_path)
    if ext in _IMAGE_EXT:
        return ImageRenderer(file_path)
    return None


class AvatarRegistry:
    def __init__(
        self,
        base_dir: str | Path,
        state_map: dict[str, str] | None = None,
        base_filename: str = "warp.mp4",
    ):
        self.base_dir = Path(base_dir)
        self.state_map = dict(state_map or {})
        self.base_filename = base_filename

    def file_for_state(self, state: str) -> Path | None:
        name = self.state_map.get(state)
        if name:
            p = self.base_dir / name
            if p.is_file():
                return p
            # Явный файл задан, но отсутствует — None.
            return None

        p = self.base_dir / self.base_filename
        if p.is_file():
            return p
        return None

    def list_missing(self) -> list[str]:
        missing: list[str] = []
        for state, name in self.state_map.items():
            if not (self.base_dir / name).is_file():
                missing.append(f"{state}: {name}")
        if not (self.base_dir / self.base_filename).is_file():
            missing.append(f"base: {self.base_filename}")
        return missing

    def ensure_base_dir(self) -> None:
        os.makedirs(self.base_dir, exist_ok=True)
