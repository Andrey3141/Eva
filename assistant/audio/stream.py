"""
AudioStream — низкоуровневая обёртка над sounddevice.InputStream.

Задача:
  - держать непрерывный поток чанков с микрофона;
  - не блокировать audio-callback: чанки кладутся в очередь;
  - давать потребителю метод get_chunk(timeout) -> np.ndarray | None;
  - корректно останавливаться и сбрасывать очередь.

Не знает ни про VAD, ни про mute/gate, ни про STT.
"""
from __future__ import annotations

import queue
import threading
from typing import Optional

import numpy as np
import sounddevice as sd

from .device import AudioInputInfo


class AudioStream:
    """
    Обёртка над sd.InputStream.
    Чанки копятся в очереди фиксированного размера.
    При переполнении — дропаем самый старый чанк.
    """

    DEFAULT_BLOCKSIZE = 1024
    DEFAULT_QUEUE_SIZE = 64

    def __init__(
        self,
        sample_rate: int,
        device: Optional[AudioInputInfo] = None,
        blocksize: int = DEFAULT_BLOCKSIZE,
        queue_size: int = DEFAULT_QUEUE_SIZE,
    ):
        self.sample_rate = int(sample_rate)
        self.device = device
        self.blocksize = int(blocksize)
        self._queue: "queue.Queue[np.ndarray]" = queue.Queue(maxsize=queue_size)
        self._stream: Optional[sd.InputStream] = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._stream is not None and self._stream.active

    # ------------------------------------------------------------------
    def start(self) -> None:
        with self._lock:
            if self._stream is not None:
                return
            device_index = self.device.index if self.device else None

            def _callback(indata, frames, time_info, status):
                chunk = np.array(indata[:, 0], dtype="float32", copy=True)
                try:
                    self._queue.put_nowait(chunk)
                except queue.Full:
                    try:
                        self._queue.get_nowait()
                    except queue.Empty:
                        pass
                    try:
                        self._queue.put_nowait(chunk)
                    except queue.Full:
                        pass

            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype="float32",
                device=device_index,
                blocksize=self.blocksize,
                callback=_callback,
            )
            self._stream.start()

    def stop(self) -> None:
        with self._lock:
            stream = self._stream
            self._stream = None
        if stream is not None:
            try:
                stream.stop()
            except Exception:
                pass
            try:
                stream.close()
            except Exception:
                pass

    # ------------------------------------------------------------------
    def get_chunk(self, timeout: float = 0.1) -> Optional[np.ndarray]:
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def clear(self) -> None:
        """Сбросить все накопленные чанки. Вызывается при mute."""
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                return
