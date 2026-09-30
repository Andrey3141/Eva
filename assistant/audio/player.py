"""
Python-нативный аудиоплеер с публикацией reference PCM для AEC.

Заменяет subprocess-based playback для WAV.
"""
import queue
import threading
import numpy as np
import sounddevice as sd


class AudioPlayer:
    def __init__(self, sample_rate: int = 48000):
        self._sample_rate = sample_rate
        self._ref_queue: "queue.Queue[np.ndarray]" = queue.Queue(maxsize=64)
        self._stop = threading.Event()
        self._stream: sd.OutputStream | None = None

    def play_pcm(self, pcm: np.ndarray) -> None:
        """Блокирующее воспроизведение PCM float32 [-1..1]."""
        ...
        # Публикуем reference-кадры для AEC
        for frame in _frames(pcm):
            try:
                self._ref_queue.put_nowait(frame)
            except queue.Full:
                try:
                    self._ref_queue.get_nowait()
                except queue.Empty:
                    pass

    def get_reference_frame(self, timeout: float = 0.05) -> np.ndarray | None:
        try:
            return self._ref_queue.get(timeout=timeout)
        except queue.Empty:
            return None
