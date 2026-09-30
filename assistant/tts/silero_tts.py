import os
import tempfile
import threading
import wave
from pathlib import Path

import numpy as np

from .base import TTSEngine
from config import Config
from assistant import paths
from assistant.audio import playback


class SileroTTS(TTSEngine):
    """
    Локальный нейросетевой TTS на базе Silero.
    Модель загружается из локального файла проекта:
        assets/silero/v4_ru.pt
    Путь корректно определяется и в исходниках, и в PyInstaller
    (через assistant.paths).

    Ленивая загрузка: модель поднимается при первом speak().
    Голос по умолчанию — xenia.
    """

    DEFAULT_SPEAKER = "xenia"
    DEFAULT_SAMPLE_RATE = 48000

    def __init__(
        self,
        speaker: str | None = None,
        model_path: str | None = None,
        sample_rate: int | None = None,
        device: str = "cpu",
    ):
        self._speaker = speaker or Config.SILERO_SPEAKER or self.DEFAULT_SPEAKER
        self._sample_rate = sample_rate or self.DEFAULT_SAMPLE_RATE
        self._device = device

        self._model_path = Path(
            model_path or paths.silero_model_path()
        )

        self._model = None
        self._lock = threading.Lock()
        self._stop_flag = threading.Event()

    # ------------------------------------------------------------------
    # Ленивая загрузка модели из локального файла
    # ------------------------------------------------------------------
    def _ensure_model(self):
        if self._model is not None:
            return self._model

        with self._lock:
            if self._model is not None:
                return self._model

            if not self._model_path.exists():
                msg = (
                    f"[TTS] Silero: локальная модель не найдена: "
                    f"{self._model_path}. "
                    f"Положите v4_ru.pt в assets/silero/."
                )
                print(msg, flush=True)
                raise FileNotFoundError(msg)

            print(
                f"[TTS] Silero: загружаю локальную модель {self._model_path}…",
                flush=True,
            )

            try:
                import torch

                torch.set_num_threads(max(1, (os.cpu_count() or 4) // 2))
                device = torch.device(self._device)

                importer = torch.package.PackageImporter(str(self._model_path))
                model = importer.load_pickle("tts_models", "model")
                model.to(device)

                self._model = model
                print("[TTS] Silero: модель загружена.", flush=True)
            except Exception as e:
                print(f"[TTS] Silero: ошибка загрузки модели: {e}", flush=True)
                raise

            return self._model

    # ------------------------------------------------------------------
    # Синтез и воспроизведение
    # ------------------------------------------------------------------
    def speak(self, text: str) -> None:
        if not text:
            return

        self._stop_flag.clear()
        model = self._ensure_model()

        print("[TTS] Silero: генерация речи…", flush=True)

        try:
            audio = model.apply_tts(
                text=text,
                speaker=self._speaker,
                sample_rate=self._sample_rate,
            )
        except Exception as e:
            print(f"[TTS] Silero: ошибка синтеза: {e}", flush=True)
            raise

        # Временный WAV — в системной временной директории, не рядом с .exe.
        fd, wav_path = tempfile.mkstemp(
            suffix=".wav",
            prefix="eva_silero_",
            dir=str(paths.temp_dir()),
        )
        os.close(fd)

        try:
            audio_np = audio.numpy()
            audio_int16 = (audio_np * 32767).astype(np.int16)

            with wave.open(wav_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(self._sample_rate)
                wf.writeframes(audio_int16.tobytes())

            print("[TTS] Silero: воспроизведение…", flush=True)
            playback.play_wav(wav_path)
        finally:
            try:
                if os.path.exists(wav_path):
                    os.remove(wav_path)
            except OSError:
                pass

    def stop(self) -> None:
        self._stop_flag.set()
