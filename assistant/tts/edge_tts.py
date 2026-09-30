import asyncio
import os
import tempfile

import edge_tts

from .base import TTSEngine
from assistant import paths
from assistant.audio import playback


class EdgeTTS(TTSEngine):
    """
    Онлайн TTS Microsoft Edge.
    Сохраняет во временный файл (в системной temp-директории),
    воспроизводит через кроссплатформенный playback.
    """

    def __init__(self, voice: str = "ru-RU-SvetlanaNeural"):
        self.voice = voice

    def speak(self, text: str) -> None:
        if not text:
            return
        asyncio.run(self._speak_async(text))

    async def _speak_async(self, text: str):
        communicate = edge_tts.Communicate(text, self.voice)

        fd, path = tempfile.mkstemp(
            suffix=".mp3",
            prefix="eva_edge_",
            dir=str(paths.temp_dir()),
        )
        os.close(fd)

        try:
            await communicate.save(path)
            playback.play_mp3(path)
        finally:
            try:
                os.remove(path)
            except OSError:
                pass
