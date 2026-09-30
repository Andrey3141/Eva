import threading

import numpy as np
from faster_whisper import WhisperModel

from .base import STTEngine
from config import Config


class WhisperSTT(STTEngine):
    """
    Ленивая обёртка над faster-whisper.
    Конструктор дешёвый: модель загружается при первом вызове transcribe().
    Загрузка защищена lock'ом, чтобы при параллельных вызовах модель
    создавалась один раз.

    ВАЖНО: transcribe() блокирует вызывающий поток на время загрузки модели
    и на время распознавания. Поэтому вызывать его нужно из фонового потока
    (см. Application._record_and_process в assistant/ui/app.py — он уже так и делает).
    """

    def __init__(
        self,
        model_size: str | None = None,
        language: str | None = None,
        device: str = "cpu",
        compute_type: str = "int8",
    ):
        self._model_size = model_size or Config.WHISPER_MODEL
        self._language = language or Config.WHISPER_LANGUAGE
        self._device = device
        self._compute_type = compute_type

        self._model: WhisperModel | None = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Ленивая загрузка
    # ------------------------------------------------------------------
    def _ensure_model(self) -> WhisperModel:
        if self._model is not None:
            return self._model

        with self._lock:
            # double-checked locking: за это время модель могла быть создана
            if self._model is not None:
                return self._model

            print(
                f"[STT] Загружаю модель Whisper "
                f"(size={self._model_size}, device={self._device}, "
                f"compute_type={self._compute_type})…",
                flush=True,
            )
            self._model = WhisperModel(
                self._model_size,
                device=self._device,
                compute_type=self._compute_type,
            )
            print("[STT] Модель загружена.", flush=True)
            return self._model

    # ------------------------------------------------------------------
    # Публичный API
    # ------------------------------------------------------------------
    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    def warmup(self) -> None:
        """
        Опционально: предзагрузить модель в фоне.
        Не вызывается по умолчанию — можно дернуть из отдельного треда,
        если позже понадобится прогревать заранее.
        """
        self._ensure_model()

    def transcribe(self, audio: np.ndarray, sample_rate: int) -> str:
        model = self._ensure_model()
        segments, _ = model.transcribe(
            audio,
            language=self._language,
            beam_size=5,
            vad_filter=True,
        )
        return " ".join(seg.text.strip() for seg in segments).strip()
