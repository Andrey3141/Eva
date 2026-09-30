"""
AEC-обёртка над pywebrtc-audio.

Принимает синхронные кадры near (mic) и far (speaker reference),
возвращает очищенный near.
"""
import numpy as np
from pywebrtc_audio import AudioProcessor

SAMPLE_RATE = 16000
FRAME_MS = 10
FRAME_SAMPLES = SAMPLE_RATE * FRAME_MS // 1000  # 160


class AecProcessor:
    def __init__(self, sample_rate: int = SAMPLE_RATE, stream_delay_ms: int = 0):
        self._ap = AudioProcessor(
            sample_rate=sample_rate,
            num_channels=1,
            echo_cancellation=True,
            noise_suppression=True,
            auto_gain_control=False,
            high_pass_filter=True,
            stream_delay_ms=stream_delay_ms,
        )
        self._sample_rate = sample_rate

    def process(self, near: np.ndarray, far: np.ndarray) -> np.ndarray:
        """near, far — float32/int16, одна длина. Возвращает очищенный near."""
        return self._ap.process(near, far)

    @property
    def speech_probability(self) -> float:
        return self._ap.speech_probability

    def reset(self) -> None:
        self._ap.reset()
