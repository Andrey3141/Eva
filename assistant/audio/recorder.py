import math
from dataclasses import dataclass
from typing import Optional

import numpy as np
import sounddevice as sd

from .device import AudioInputInfo, describe_device


@dataclass
class RecordingResult:
    audio: Optional[np.ndarray]      # None, если сигнала нет
    sample_rate: int
    duration_sec: float
    rms: float
    peak: float
    is_silent: bool
    device: Optional[AudioInputInfo]
    message: str = ""


def _safe(x) -> float:
    """Защита от NaN/Inf/None — некоторые драйверы могут вернуть мусор."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return 0.0
    if math.isnan(v) or math.isinf(v):
        return 0.0
    return v


class AudioRecorder:
    """
    Записывает с выбранного физического устройства ввода.
    Не использует monitor of ... в качестве микрофона.
    Возвращает результат с оценкой RMS/peak, чтобы вызывающий код
    мог решить, отправлять ли запись в Whisper.
    """

    DEFAULT_RMS_THRESHOLD = 0.005
    HARD_FLOOR = 0.0015

    def __init__(
        self,
        sample_rate: int,
        duration_sec: float,
        device: Optional[AudioInputInfo] = None,
        rms_threshold: float = DEFAULT_RMS_THRESHOLD,
    ):
        self.sample_rate = int(sample_rate)
        self.duration_sec = float(duration_sec)
        self.device = device
        self.rms_threshold = float(rms_threshold)

    def record(self) -> RecordingResult:
        frames = int(self.duration_sec * self.sample_rate)

        try:
            audio = sd.rec(
                frames,
                samplerate=self.sample_rate,
                channels=1,
                dtype="float32",
                device=(self.device.index if self.device else None),
            )
            sd.wait()
        except Exception as e:
            return RecordingResult(
                audio=None,
                sample_rate=self.sample_rate,
                duration_sec=self.duration_sec,
                rms=0.0,
                peak=0.0,
                is_silent=True,
                device=self.device,
                message=f"Ошибка записи: {e}",
            )

        audio = np.asarray(audio).flatten()
        if audio.size == 0:
            return RecordingResult(
                audio=None,
                sample_rate=self.sample_rate,
                duration_sec=self.duration_sec,
                rms=0.0,
                peak=0.0,
                is_silent=True,
                device=self.device,
                message="Запись пустая.",
            )

        # Считаем RMS/peak в float64, затем прогоняем через _safe,
        # чтобы NaN/Inf не сломали проверку тишины.
        rms_raw = float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))
        peak_raw = float(np.max(np.abs(audio)))

        rms = _safe(rms_raw)
        peak = _safe(peak_raw)

        is_silent = (
            (rms < self.rms_threshold and peak < self.rms_threshold * 6)
            or (peak < self.HARD_FLOOR)
        )

        message = ""
        if is_silent:
            message = (
                f"RMS={rms:.5f}, peak={peak:.5f}. "
                f"Входной сигнал отсутствует или слишком тихий."
            )

        return RecordingResult(
            audio=audio if not is_silent else None,
            sample_rate=self.sample_rate,
            duration_sec=self.duration_sec,
            rms=rms,
            peak=peak,
            is_silent=is_silent,
            device=self.device,
            message=message,
        )

    @staticmethod
    def format_device(d: Optional[AudioInputInfo]) -> str:
        return describe_device(d)
