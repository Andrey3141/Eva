"""
ContinuousListener — непрерывное прослушивание микрофона.

Архитектура:

    sd.InputStream (audio callback)
            │
            ▼
       chunk_queue
            │
            │ VAD-thread  (непрерывно, не блокируется на core)
            ▼
       segment_queue
            │
            │ core-worker-thread  (последовательно, один handle_audio за раз)
            ▼
       on_segment(audio, sample_rate)

Свойства:
  - muted по умолчанию True. При muted=True stream не запущен.
  - gate: пока TTS говорит (SPEAKING), gate_closed=True — чанки дропаются,
    активный буфер сегмента сбрасывается.
  - VAD-thread никогда не вызывает on_segment. Только кладёт сегменты
    в segment_queue.
  - core-worker-thread берёт сегменты последовательно и вызывает
    on_segment. Если core занят, VAD продолжает нарезать новые сегменты,
    они копятся в segment_queue и не теряются.
"""
from __future__ import annotations

import queue
import threading
import time
from typing import Callable, Optional

import numpy as np

from .device import AudioInputInfo
from .stream import AudioStream


SegmentCallback = Callable[[np.ndarray, int], None]


class ContinuousListener:
    # Пороги VAD (RMS).
    SPEECH_RMS = 0.012
    SILENCE_RMS = 0.007

    MIN_SEGMENT_MS = 300
    MIN_SILENCE_MS = 700
    MAX_SEGMENT_MS = 15000

    # Очередь готовых сегментов, ожидающих обработки core.
    SEGMENT_QUEUE_SIZE = 32

    # Небольшая пауза после закрытия gate, чтобы хвост TTS не попал в STT.
    POST_TTS_GRACE_SEC = 0.2

    def __init__(
        self,
        sample_rate: int,
        on_segment: SegmentCallback,
        device: Optional[AudioInputInfo] = None,
        muted: bool = True,
    ):
        self.sample_rate = int(sample_rate)
        self.on_segment = on_segment
        self.device = device

        self._muted = bool(muted)
        self._gate_open = True
        self._gate_reopen_at: float = 0.0
        self._gate_lock = threading.Lock()

        self._stream: Optional[AudioStream] = None
        self._vad_thread: Optional[threading.Thread] = None
        self._worker_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

        self._segment_queue: "queue.Queue[np.ndarray]" = queue.Queue(
            maxsize=self.SEGMENT_QUEUE_SIZE
        )

    # ------------------------------------------------------------------
    # Публичный API
    # ------------------------------------------------------------------
    @property
    def muted(self) -> bool:
        return self._muted

    @property
    def listening(self) -> bool:
        return not self._muted

    def start(self) -> None:
        with self._lock:
            if self._worker_thread is None or not self._worker_thread.is_alive():
                self._worker_thread = threading.Thread(
                    target=self._worker_loop, daemon=True, name="eva-core-worker",
                )
                self._worker_thread.start()
            if self._vad_thread is None or not self._vad_thread.is_alive():
                self._stop_event.clear()
                self._vad_thread = threading.Thread(
                    target=self._vad_loop, daemon=True, name="eva-vad",
                )
                self._vad_thread.start()

        if not self._muted:
            self._start_stream()

    def stop(self) -> None:
        self._stop_event.set()
        self._stop_stream()
        # Разбудить worker, если он висит на queue.get
        try:
            self._segment_queue.put_nowait(np.zeros(0, dtype="float32"))
        except queue.Full:
            pass
        for t in (self._vad_thread, self._worker_thread):
            if t is not None:
                t.join(timeout=2.0)
        self._vad_thread = None
        self._worker_thread = None

    def set_muted(self, muted: bool) -> None:
        muted = bool(muted)
        if muted == self._muted:
            return
        self._muted = muted
        if muted:
            self._stop_stream()
            # Сбросить накопленное, чтобы «хвост» не ушёл в Core.
            if self._stream is not None:
                self._stream.clear()
            try:
                # Дропнуть уже накопленные сегменты, они относятся к mute-периоду.
                while True:
                    self._segment_queue.get_nowait()
            except queue.Empty:
                pass
        else:
            self._start_stream()

    # ------------------------------------------------------------------
    # Gate (блокировка на время TTS)
    # ------------------------------------------------------------------
    def open_gate(self) -> None:
        with self._gate_lock:
            self._gate_open = True
            self._gate_reopen_at = 0.0

    def close_gate(self, grace_sec: Optional[float] = None) -> None:
        with self._gate_lock:
            self._gate_open = False
            grace = self.POST_TTS_GRACE_SEC if grace_sec is None else grace_sec
            self._gate_reopen_at = time.monotonic() + grace

    def _is_gate_open(self) -> bool:
        with self._gate_lock:
            if not self._gate_open and time.monotonic() >= self._gate_reopen_at:
                self._gate_open = True
            return self._gate_open

    # ------------------------------------------------------------------
    # Потоки
    # ------------------------------------------------------------------
    def _start_stream(self) -> None:
        if self._stream is None:
            self._stream = AudioStream(
                sample_rate=self.sample_rate,
                device=self.device,
            )
        self._stream.start()

    def _stop_stream(self) -> None:
        if self._stream is not None:
            self._stream.stop()

    def _vad_loop(self) -> None:
        """
        Непрерывно читает чанки из stream, нарезает сегменты,
        кладёт в segment_queue. НИКОГДА не вызывает on_segment.
        """
        segment_chunks: list[np.ndarray] = []
        in_speech = False
        silence_started: Optional[float] = None
        segment_started_at: Optional[float] = None

        while not self._stop_event.is_set():
            stream = self._stream
            if stream is None or not stream.is_running or self._muted:
                time.sleep(0.05)
                continue

            chunk = stream.get_chunk(timeout=0.1)
            if chunk is None:
                continue

            if not self._is_gate_open():
                # Во время TTS сбрасываем активный буфер и дропаем.
                segment_chunks.clear()
                in_speech = False
                silence_started = None
                segment_started_at = None
                continue

            rms = float(np.sqrt(np.mean(chunk.astype(np.float64) ** 2)))
            now = time.monotonic()

            if not in_speech:
                if rms >= self.SPEECH_RMS:
                    in_speech = True
                    silence_started = None
                    segment_started_at = now
                    segment_chunks = [chunk]
                continue

            segment_chunks.append(chunk)

            if segment_started_at is not None:
                if (now - segment_started_at) * 1000.0 >= self.MAX_SEGMENT_MS:
                    self._enqueue_segment(segment_chunks)
                    segment_chunks = []
                    in_speech = False
                    silence_started = None
                    segment_started_at = None
                    continue

            if rms < self.SILENCE_RMS:
                if silence_started is None:
                    silence_started = now
                elif (now - silence_started) * 1000.0 >= self.MIN_SILENCE_MS:
                    self._enqueue_segment(segment_chunks)
                    segment_chunks = []
                    in_speech = False
                    silence_started = None
                    segment_started_at = None
            else:
                silence_started = None

        # На выходе — если что-то накопилось, отдать.
        if segment_chunks:
            self._enqueue_segment(segment_chunks)

    def _enqueue_segment(self, chunks: list[np.ndarray]) -> None:
        if not chunks:
            return
        audio = np.concatenate(chunks).astype("float32", copy=False)
        duration_ms = (audio.size / self.sample_rate) * 1000.0
        if duration_ms < self.MIN_SEGMENT_MS:
            return
        try:
            self._segment_queue.put_nowait(audio)
        except queue.Full:
            # Отстаём: дропаем самый старый сегмент, чтобы не терять новый.
            try:
                self._segment_queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self._segment_queue.put_nowait(audio)
            except queue.Full:
                print("[Listener] segment queue full, dropping segment",
                      flush=True)

    def _worker_loop(self) -> None:
        """
        Берёт сегменты из очереди последовательно и вызывает on_segment.
        Один handle_audio за раз. Пока этот поток работает, VAD-поток
        продолжает наполнять очередь.
        """
        while not self._stop_event.is_set():
            try:
                audio = self._segment_queue.get(timeout=0.2)
            except queue.Empty:
                continue

            if audio.size == 0:
                # Служебный маркер разбудить worker при stop()
                continue

            try:
                self.on_segment(audio, self.sample_rate)
            except Exception as e:
                print(f"[Listener] on_segment error: {e}", flush=True)
