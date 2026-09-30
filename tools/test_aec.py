"""
POC: WebRTC AEC3 через pywebrtc-audio в реальном акустическом тракте.

ЦЕЛЬ POC
--------
Доказать, что схема

    TTS PCM -> speaker -> воздух -> mic -> WebRTC AEC3

реально подавляет голос Алисы и при этом НЕ уничтожает человеческую речь.

POC полностью отдельный. EVA и её файлы не трогаются.
AecProcessor в EVA существует, но в рабочем аудиопути пока не вызывается —
здесь мы это проверяем до интеграции.

ЗАПУСК (первый акустический прогон)
------------------------------------
    # 1. Список устройств
    python -m tools.test_aec --list

    # 2. Один простой тест A, без sweep, оба delay = 0
    python -m tools.test_aec --input <ID> --output <ID> --test a

    # 3. Тест B: динамик + человек (говорите в микрофон во время сигнала)
    python -m tools.test_aec --input <ID> --output <ID> --test b

    # 4. Реальный WAV как reference
    python -m tools.test_aec --input <ID> --output <ID> \
        --reference /path/to/silero_output.wav \
        --signal-start-ms 500 --signal-end-ms 3500

МОДЕЛЬ ЗАДЕРЖЕК (важно)
------------------------
Есть ДВЕ независимые задержки, и их нельзя смешивать:

    --far-offset-ms
        Сдвиг reference относительно mic в нашей модели:
            far_block(t) = reference[mic_pos - far_offset_samples]
        Это МОДЕЛЬ того, насколько reference, поданный в AEC, должен
        опережать mic. По умолчанию 0 — AEC сам оценивает задержку.
        НЕ влияет на metric window.

    --stream-delay-ms
        Hint для AudioProcessor(stream_delay_ms=...). Это параметр
        самого WebRTC AEC3. По умолчанию 0 — AEC3 использует
        внутреннюю оценку задержки.
        НЕ влияет на metric window.

time_info.inputBufferAdcTime / outputBufferDacTime НЕ используются.
Синхронизация — модель фиксированного смещения. Полноценная clock
synchronization будет отдельным шагом после доказательства AEC.

ОКНО МЕТРИК (важно)
--------------------
Reference имеет структуру:
    0.0 .. signal_start_ms             тишина (head)
    signal_start_ms .. signal_end_ms   сигнал
    signal_end_ms .. +tail             тишина

Эхо приходит в mic С ЗАДЕРЖКОЙ. Эту задержку мы НЕ вычисляем как
far_offset_ms + stream_delay_ms — это параметры настройки алгоритма,
а не измеренная акустическая задержка.

Физическую задержку определяем по реальной записи:

    speaker_ref -> акустический тракт -> mic_raw
                    (xcorr_lag_ms)

Metric-окно строится по ней:
    lag = max(0, xcorr_lag_ms)
    metric_start_ms = signal_start_ms + lag
    metric_end_ms   = signal_end_ms   + lag

Порядок в compute_metrics():
    1. xcorr на активном reference-окне -> xcorr_lag_ms.
    2. Сдвиг metric-окна на max(0, xcorr_lag_ms).
    3. RMS/attenuation на metric-окне.

xcorr_lag_ms целочисленный (16 сэмплов при 16 кГц). Субсэмпловую оценку
добавим отдельно, если понадобится.

В JSON сохраняются раздельно:
    ref_signal_start_ms, ref_signal_end_ms   — структура reference
    xcorr_peak, xcorr_lag_ms                 — измеренная задержка
    metric_start_ms, metric_end_ms           — окно, где считались RMS
    far_offset_ms, stream_delay_ms           — параметры прогона

МЕТРИКИ
-------
Для каждого прогона сохраняются:
    mic_raw_<tag>.wav       — что слышал микрофон
    speaker_ref_<tag>.wav   — что реально ушло в динамик
    mic_after_aec_<tag>.wav — что вернул AEC
    report_<tag>.json       — цифры

Основные цифры (на metric-окне):
    rms_raw_echo_only / rms_aec_echo_only / attenuation_echo_only_db
    xcorr_peak / xcorr_lag_ms
        Диагностика: подтверждает, что reference коррелирует с mic,
        и показывает фактический лаг. НЕ является доказательством
        качества AEC.
    rtf
        Real-time factor процесса AEC.

attenuation_echo_only_db НЕ является автоматическим verdict'ом.
Главный критерий — прослушать WAV'ы:
    Тест A: после AEC эхо подавлено.
    Тест B: после AEC человеческая речь ОСТАЛАСЬ.
"""

from __future__ import annotations

import argparse
import json
import math
import queue
import sys
import threading
import time
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import sounddevice as sd

try:
    from pywebrtc_audio import AudioProcessor
except Exception as e:  # noqa: BLE001
    print(f"[AEC-POC] pywebrtc-audio не установлен: {e}", flush=True)
    print("[AEC-POC] Установите: pip install pywebrtc-audio", flush=True)
    sys.exit(3)


SAMPLE_RATE = 16000
CHANNELS = 1
DTYPE = "float32"

# 10 ms. Библиотека pywebrtc-audio работает с 10-мс кадрами,
# её realtime-пример использует 160 samples при 16 кГц.
# Production pipeline EVA сейчас использует 1024; это будет приведено
# к совместимому размеру ОТДЕЛЬНО, после успешного POC.
BLOCKSIZE = 160

# Структура синтетического reference (сек).
REF_SILENCE_HEAD_SEC = 0.5
REF_SIGNAL_SEC = 3.0
REF_SILENCE_TAIL_SEC = 0.4

# Окно reference, на котором считается сигнал (мс).
DEFAULT_SIGNAL_START_MS = 500
DEFAULT_SIGNAL_END_MS = 3500

# Сколько ещё писать mic после конца reference, чтобы поймать echo tail.
DEFAULT_ECHO_TAIL_MS = 400


# ---------------------------------------------------------------------------
# WAV I/O
# ---------------------------------------------------------------------------

def _read_wav_mono_16k(path: Path) -> np.ndarray:
    """Читает WAV (int16/int32/uint8), возвращает float32 mono 16 kHz [-1, 1]."""
    with wave.open(str(path), "rb") as wf:
        sr = wf.getframerate()
        n_ch = wf.getnchannels()
        sw = wf.getsampwidth()
        n_frames = wf.getnframes()
        raw = wf.readframes(n_frames)

    if sw == 2:
        data = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    elif sw == 4:
        data = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
    elif sw == 1:
        data = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    else:
        raise ValueError(f"unsupported sample width: {sw}")

    if n_ch > 1:
        data = data.reshape(-1, n_ch).mean(axis=1)

    if sr != SAMPLE_RATE:
        data = _resample_linear(data, sr, SAMPLE_RATE)

    return data.astype(np.float32, copy=False)


def _resample_linear(x: np.ndarray, sr_in: int, sr_out: int) -> np.ndarray:
    """Линейный ресемплер. Для POC достаточно — качество AEC не критично."""
    if sr_in == sr_out:
        return x
    n_out = int(round(len(x) * sr_out / sr_in))
    t_in = np.linspace(0.0, 1.0, num=len(x), endpoint=False)
    t_out = np.linspace(0.0, 1.0, num=n_out, endpoint=False)
    return np.interp(t_out, t_in, x).astype(np.float32)


def _write_wav_mono_16k(path: Path, x: np.ndarray) -> None:
    """Пишет float32 [-1, 1] как int16 WAV."""
    clipped = np.clip(x, -1.0, 1.0)
    pcm = (clipped * 32767.0).astype("<i2")
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm.tobytes())


# ---------------------------------------------------------------------------
# Устройства
# ---------------------------------------------------------------------------

@dataclass
class DeviceInfo:
    index: int
    name: str
    channels: int
    default_samplerate: float
    hostapi: str


def list_devices() -> tuple[list[DeviceInfo], list[DeviceInfo]]:
    devices = sd.query_devices()
    hostapis = sd.query_hostapis()
    ins: list[DeviceInfo] = []
    outs: list[DeviceInfo] = []
    for i, d in enumerate(devices):
        ha_idx = int(d.get("hostapi", 0) or 0)
        ha = hostapis[ha_idx]["name"] if ha_idx < len(hostapis) else "?"
        info = DeviceInfo(
            index=i,
            name=str(d.get("name", "")),
            channels=int(d.get("max_input_channels", 0) or 0),
            default_samplerate=float(d.get("default_samplerate", 0) or 0),
            hostapi=ha,
        )
        if info.channels > 0:
            ins.append(info)
        if int(d.get("max_output_channels", 0) or 0) > 0:
            outs.append(info)
    return ins, outs


def print_devices() -> None:
    ins, outs = list_devices()
    print("[AEC-POC] Input devices:", flush=True)
    for d in ins:
        print(f"  {d.index}: {d.name}  hostapi={d.hostapi}  "
              f"ch={d.channels}  sr={d.default_samplerate:.0f}", flush=True)
    print("[AEC-POC] Output devices:", flush=True)
    for d in outs:
        print(f"  {d.index}: {d.name}  hostapi={d.hostapi}  "
              f"ch={d.channels}  sr={d.default_samplerate:.0f}", flush=True)


# ---------------------------------------------------------------------------
# Результат прогона
# ---------------------------------------------------------------------------

@dataclass
class AecRunResult:
    mic_raw: np.ndarray
    speaker_ref: np.ndarray
    mic_after_aec: np.ndarray
    process_time_total: float
    audio_seconds: float
    # Параметры прогона (настройка алгоритма, НЕ физическая задержка).
    test: str
    far_offset_ms: int
    stream_delay_ms: int
    volume: float
    blocksize: int
    echo_tail_ms: int
    # Reference-окно (структура теста).
    ref_signal_start_ms: int
    ref_signal_end_ms: int
    # Фактическая акустическая задержка, измеренная по xcorr.
    xcorr_peak: float = 0.0
    xcorr_lag_ms: int = 0
    # Metric-окно = ref-окно + max(0, xcorr_lag_ms).
    metric_start_ms: int = 0
    metric_end_ms: int = 0
    # Метрики на metric-окне.
    rms_raw_echo_only: float = 0.0
    rms_aec_echo_only: float = 0.0
    attenuation_echo_only_db: float = 0.0
    # Полные метрики — для справки.
    rms_raw_full: float = 0.0
    rms_aec_full: float = 0.0
    # Производительность.
    rtf: float = 0.0

    def as_dict(self) -> dict:
        return {
            # Параметры прогона (настройка алгоритма, НЕ физическая задержка).
            "test": self.test,
            "far_offset_ms": self.far_offset_ms,
            "stream_delay_ms": self.stream_delay_ms,
            "volume": self.volume,
            "blocksize": self.blocksize,
            "echo_tail_ms": self.echo_tail_ms,

            # Reference-окно (структура теста).
            "ref_signal_start_ms": self.ref_signal_start_ms,
            "ref_signal_end_ms": self.ref_signal_end_ms,

            # Фактическая акустическая задержка, измеренная по xcorr
            # между speaker_ref и mic_raw. Именно она используется для
            # сдвига metric-окна.
            "xcorr_peak": self.xcorr_peak,
            "xcorr_lag_ms": self.xcorr_lag_ms,

            # Metric-окно = ref-окно + max(0, xcorr_lag_ms).
            "metric_start_ms": self.metric_start_ms,
            "metric_end_ms": self.metric_end_ms,

            # Метрики на metric-окне.
            "rms_raw_echo_only": self.rms_raw_echo_only,
            "rms_aec_echo_only": self.rms_aec_echo_only,
            "attenuation_echo_only_db": self.attenuation_echo_only_db,

            # Полные метрики — для справки.
            "rms_raw_full": self.rms_raw_full,
            "rms_aec_full": self.rms_aec_full,

            # Производительность.
            "rtf": self.rtf,
            "process_time_total": self.process_time_total,
            "audio_seconds": self.audio_seconds,
        }


# ---------------------------------------------------------------------------
# Дуплекс + AEC
# ---------------------------------------------------------------------------

class SynchronizedDuplexAec:
    """
    Дуплексный AEC.

    ДВЕ РАЗНЫЕ ЗАДЕРЖКИ:

      far_offset_ms
          Сдвиг reference относительно mic в нашей модели:
              far_block(t) = reference[mic_pos - far_offset_samples]
          Это модель того, насколько reference, поданный в AEC, должен
          опережать mic. По умолчанию 0 — AEC сам оценивает задержку.
          НЕ влияет на metric window.

      stream_delay_ms
          Hint для AudioProcessor(stream_delay_ms=...). Это параметр
          самого WebRTC AEC3. По умолчанию 0 — AEC3 использует
          внутреннюю оценку задержки.
          НЕ влияет на metric window.

    time_info НЕ используется. Синхронизация — модель фиксированного
    смещения (см. docstring модуля).
    """

    def __init__(
        self,
        reference: np.ndarray,
        input_device: Optional[int],
        output_device: Optional[int],
        far_offset_ms: int,
        stream_delay_ms: int,
        blocksize: int = BLOCKSIZE,
        volume: float = 1.0,
        echo_tail_ms: int = DEFAULT_ECHO_TAIL_MS,
    ):
        self.reference = reference.astype(np.float32, copy=False)
        self.input_device = input_device
        self.output_device = output_device
        self.far_offset_ms = int(far_offset_ms)
        self.stream_delay_ms = int(stream_delay_ms)
        self.blocksize = int(blocksize)
        self.volume = float(volume)
        self.echo_tail_samples = int(SAMPLE_RATE * echo_tail_ms / 1000)

        self._ap = AudioProcessor(
            sample_rate=SAMPLE_RATE,
            num_channels=CHANNELS,
            echo_cancellation=True,
            noise_suppression=True,
            high_pass_filter=True,
            auto_gain_control=False,
            stream_delay_ms=self.stream_delay_ms,
        )

        self._ref_pos = 0
        self._mic_pos = 0

        # Модель фиксированного смещения для far_block.
        self._far_offset_samples = int(SAMPLE_RATE * self.far_offset_ms / 1000)

        self._mic_raw_chunks: list[np.ndarray] = []
        self._mic_aec_chunks: list[np.ndarray] = []
        self._ref_chunks: list[np.ndarray] = []
        self._process_time = 0.0
        self._status_flags: list[str] = []

        self._tail_remaining = self.echo_tail_samples

    # ------------------------------------------------------------------
    def _callback(self, indata, outdata, frames, time_info, status):
        # time_info намеренно не используется — см. docstring класса.
        _ = time_info

        if status:
            self._status_flags.append(str(status))

        # 1. Reference -> outdata (с множителем громкости PCM).
        ref_block = np.zeros(frames, dtype=np.float32)
        n_avail = min(frames, len(self.reference) - self._ref_pos)
        if n_avail > 0:
            chunk = self.reference[self._ref_pos:self._ref_pos + n_avail]
            ref_block[:n_avail] = chunk * self.volume
            self._ref_pos += n_avail
        outdata[:, 0] = ref_block

        # 2. Mic <- indata.
        mic_block = indata[:, 0].astype(np.float32, copy=True)

        # 3. Fixed-offset far. Только far_offset_samples, БЕЗ stream_delay.
        s = self._mic_pos
        far_start = s - self._far_offset_samples
        far_block = np.zeros(frames, dtype=np.float32)
        if far_start >= 0 and far_start + frames <= len(self.reference):
            far_block[:] = self.reference[far_start:far_start + frames] * self.volume
        # иначе — нули (до начала или после конца reference).

        # 4. AEC3: near=mic_block, far=far_block.
        t0 = time.perf_counter()
        try:
            clean = self._ap.process(mic_block, far_block)
        except Exception as e:  # noqa: BLE001
            print(f"[AEC-POC] AEC process error: {e}", flush=True)
            clean = mic_block.copy()
        dt = time.perf_counter() - t0

        self._process_time += dt
        self._mic_raw_chunks.append(mic_block)
        self._mic_aec_chunks.append(clean.astype(np.float32, copy=True))
        self._ref_chunks.append(ref_block.copy())

        self._mic_pos += frames

        # 5. Остановка: reference закончился И tail дозаписан.
        if self._ref_pos >= len(self.reference):
            if self._tail_remaining > 0:
                self._tail_remaining -= frames
            else:
                raise sd.CallbackStop()

    # ------------------------------------------------------------------
    def run(self) -> tuple[np.ndarray, np.ndarray, np.ndarray, float, float]:
        with sd.Stream(
            samplerate=SAMPLE_RATE,
            blocksize=self.blocksize,
            dtype=DTYPE,
            channels=CHANNELS,
            device=(self.input_device, self.output_device),
            callback=self._callback,
        ) as stream:
            stream.start()
            hard_timeout = (len(self.reference) / SAMPLE_RATE) + 5.0
            t0 = time.monotonic()
            while stream.active and (time.monotonic() - t0) < hard_timeout:
                time.sleep(0.05)
            stream.stop()

        mic_raw = np.concatenate(self._mic_raw_chunks) if self._mic_raw_chunks \
            else np.zeros(0, dtype=np.float32)
        mic_aec = np.concatenate(self._mic_aec_chunks) if self._mic_aec_chunks \
            else np.zeros(0, dtype=np.float32)
        ref = np.concatenate(self._ref_chunks) if self._ref_chunks \
            else np.zeros(0, dtype=np.float32)

        n = min(len(mic_raw), len(mic_aec), len(ref))
        mic_raw = mic_raw[:n]
        mic_aec = mic_aec[:n]
        ref = ref[:n]

        audio_seconds = n / SAMPLE_RATE if n else 0.0
        rtf = audio_seconds / self._process_time if self._process_time > 0 else 0.0

        return mic_raw, ref, mic_aec, self._process_time, rtf


# ---------------------------------------------------------------------------
# Метрики
# ---------------------------------------------------------------------------

def _rms(x: np.ndarray) -> float:
    if x.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(x.astype(np.float64) ** 2)))


def _attenuation_db(rms_before: float, rms_after: float) -> float:
    if rms_before <= 0 and rms_after <= 0:
        return 0.0
    if rms_after <= 0:
        return float("inf")
    if rms_before <= 0:
        return 0.0
    return 20.0 * math.log10(rms_before / rms_after)


def _slice_ms(x: np.ndarray, start_ms: int, end_ms: int) -> np.ndarray:
    a = max(0, int(SAMPLE_RATE * start_ms / 1000))
    b = min(len(x), int(SAMPLE_RATE * end_ms / 1000))
    if b <= a:
        return np.zeros(0, dtype=x.dtype)
    return x[a:b]


def _xcorr_lag(
    ref: np.ndarray,
    mic: np.ndarray,
    active_start_ms: int,
    active_end_ms: int,
    max_lag_ms: int = 200,
) -> tuple[float, int]:
    """
    Cross-correlation ref vs mic ТОЛЬКО на активном reference-окне.

    Диагностика + измерение фактической акустической задержки
    reference vs mic.

    ВАЖНО: сам по себе xcorr_peak НЕ является доказательством качества AEC.
    Он нужен для:
      1. подтверждения, что reference действительно коррелирует с mic;
      2. определения фактической задержки акустического тракта,
         по которой сдвигается metric-окно.

    Возвращает (peak_value, lag_ms). lag_ms целочисленный —
    дискретность 16 сэмплов при 16 кГц. Для POC этого достаточно.
    """
    ref_seg = _slice_ms(ref, active_start_ms, active_end_ms)
    mic_seg = _slice_ms(mic, active_start_ms, active_end_ms)
    n = min(len(ref_seg), len(mic_seg))
    if n == 0:
        return 0.0, 0
    ref_seg = ref_seg[:n] - float(np.mean(ref_seg[:n]))
    mic_seg = mic_seg[:n] - float(np.mean(mic_seg[:n]))

    max_lag = int(SAMPLE_RATE * max_lag_ms / 1000)
    max_lag = min(max_lag, n - 1)
    if max_lag <= 0:
        return 0.0, 0

    corr = np.correlate(mic_seg, ref_seg, mode="full")
    center = len(ref_seg) - 1
    lo = max(0, center - max_lag)
    hi = min(len(corr) - 1, center + max_lag)
    window = corr[lo:hi + 1]
    if window.size == 0:
        return 0.0, 0

    peak_idx = int(np.argmax(np.abs(window))) + lo
    lag = peak_idx - center
    peak_val = float(corr[peak_idx])
    denom = float(np.sqrt(np.sum(ref_seg ** 2) * np.sum(mic_seg ** 2)))
    if denom > 0:
        peak_val = peak_val / denom
    return peak_val, int(lag * 1000 / SAMPLE_RATE)


def compute_metrics(
    result: AecRunResult,
    ref_signal_start_ms: int,
    ref_signal_end_ms: int,
) -> None:
    """
    Считает метрики на окне, сдвинутом на ФАКТИЧЕСКУЮ акустическую задержку.

    ВАЖНО: far_offset_ms и stream_delay_ms — это параметры настройки
    алгоритма, а НЕ измеренная задержка акустического тракта.
    Физическую задержку определяем по xcorr между speaker_ref и mic_raw:

        speaker_ref -> акустический тракт -> mic_raw
                        (xcorr_lag_ms)

    Порядок:
      1. xcorr на активном reference-окне -> xcorr_lag_ms.
      2. lag = max(0, xcorr_lag_ms).
      3. metric_start_ms = ref_signal_start_ms + lag
         metric_end_ms   = ref_signal_end_ms   + lag
      4. RMS/attenuation считаем на metric-окне.

    xcorr_lag_ms целочисленный (дискретность 16 сэмплов при 16 кГц).
    Для POC этого достаточно; субсэмпловая оценка — отдельный шаг.
    """
    # 1. Фактический лаг reference vs mic.
    result.xcorr_peak, result.xcorr_lag_ms = _xcorr_lag(
        result.speaker_ref, result.mic_raw,
        ref_signal_start_ms, ref_signal_end_ms,
    )

    # 2. Metric-окно сдвигаем только на измеренный лаг.
    lag = max(0, result.xcorr_lag_ms)
    result.ref_signal_start_ms = ref_signal_start_ms
    result.ref_signal_end_ms = ref_signal_end_ms
    result.metric_start_ms = ref_signal_start_ms + lag
    result.metric_end_ms = ref_signal_end_ms + lag

    # 3. RMS на metric-окне.
    raw_echo = _slice_ms(result.mic_raw, result.metric_start_ms, result.metric_end_ms)
    aec_echo = _slice_ms(result.mic_after_aec, result.metric_start_ms, result.metric_end_ms)

    result.rms_raw_echo_only = _rms(raw_echo)
    result.rms_aec_echo_only = _rms(aec_echo)
    result.attenuation_echo_only_db = _attenuation_db(
        result.rms_raw_echo_only, result.rms_aec_echo_only
    )

    # 4. Полные метрики — справочно.
    result.rms_raw_full = _rms(result.mic_raw)
    result.rms_aec_full = _rms(result.mic_after_aec)


# ---------------------------------------------------------------------------
# Reference
# ---------------------------------------------------------------------------

def make_synthetic_reference(
    signal_sec: float = REF_SIGNAL_SEC,
    silence_head_sec: float = REF_SILENCE_HEAD_SEC,
    silence_tail_sec: float = REF_SILENCE_TAIL_SEC,
) -> np.ndarray:
    """
    Синтетический reference:
        0 .. silence_head_sec          тишина
        .. + signal_sec                chirp 200..2000 Hz
        .. + silence_tail_sec          тишина (echo tail)
    """
    sr = SAMPLE_RATE
    n_head = int(sr * silence_head_sec)
    n_sig = int(sr * signal_sec)
    n_tail = int(sr * silence_tail_sec)
    n = n_head + n_sig + n_tail

    x = np.zeros(n, dtype=np.float32)
    t = np.arange(n_sig, dtype=np.float32) / sr
    f0, f1 = 200.0, 2000.0
    k = (f1 - f0) / max(signal_sec, 1e-6)
    phase = 2 * np.pi * (f0 * t + 0.5 * k * t * t)
    x[n_head:n_head + n_sig] = 0.6 * np.sin(phase).astype(np.float32)
    return x


def load_reference_wav(
    path: Path,
    signal_start_ms: int,
    signal_end_ms: int,
    silence_head_sec: float = REF_SILENCE_HEAD_SEC,
    silence_tail_sec: float = REF_SILENCE_TAIL_SEC,
) -> np.ndarray:
    x = _read_wav_mono_16k(path)
    if signal_end_ms > signal_start_ms:
        x = _slice_ms(x, signal_start_ms, signal_end_ms)
    head = np.zeros(int(SAMPLE_RATE * silence_head_sec), dtype=np.float32)
    tail = np.zeros(int(SAMPLE_RATE * silence_tail_sec), dtype=np.float32)
    return np.concatenate([head, x.astype(np.float32), tail])


# ---------------------------------------------------------------------------
# Один прогон
# ---------------------------------------------------------------------------

def _tag(test: str, far_offset_ms: int, stream_delay_ms: int, volume: float) -> str:
    return (f"{test}_fo{far_offset_ms}_sd{stream_delay_ms}"
            f"_v{int(round(volume*100)):03d}")


def run_one(
    reference: np.ndarray,
    input_device: Optional[int],
    output_device: Optional[int],
    far_offset_ms: int,
    stream_delay_ms: int,
    volume: float,
    test: str,
    outdir: Path,
    blocksize: int,
    echo_tail_ms: int,
    ref_signal_start_ms: int,
    ref_signal_end_ms: int,
) -> AecRunResult:
    tag = _tag(test, far_offset_ms, stream_delay_ms, volume)
    print(f"\n[AEC-POC] === test={test} "
          f"far_offset={far_offset_ms}ms stream_delay={stream_delay_ms}ms "
          f"volume={volume:.2f} blocksize={blocksize} ({tag}) ===", flush=True)
    if test == "b":
        print("[AEC-POC] TEST B: говорите в микрофон во время сигнала.", flush=True)

    runner = SynchronizedDuplexAec(
        reference=reference,
        input_device=input_device,
        output_device=output_device,
        far_offset_ms=far_offset_ms,
        stream_delay_ms=stream_delay_ms,
        blocksize=blocksize,
        volume=volume,
        echo_tail_ms=echo_tail_ms,
    )
    mic_raw, ref, mic_aec, process_time, rtf = runner.run()

    audio_seconds = len(mic_raw) / SAMPLE_RATE if len(mic_raw) else 0.0
    result = AecRunResult(
        mic_raw=mic_raw,
        speaker_ref=ref,
        mic_after_aec=mic_aec,
        process_time_total=process_time,
        audio_seconds=audio_seconds,
        test=test,
        far_offset_ms=far_offset_ms,
        stream_delay_ms=stream_delay_ms,
        volume=volume,
        blocksize=blocksize,
        echo_tail_ms=echo_tail_ms,
        ref_signal_start_ms=ref_signal_start_ms,
        ref_signal_end_ms=ref_signal_end_ms,
        rtf=rtf,
    )
    compute_metrics(
        result,
        ref_signal_start_ms=ref_signal_start_ms,
        ref_signal_end_ms=ref_signal_end_ms,
    )

    outdir.mkdir(parents=True, exist_ok=True)
    _write_wav_mono_16k(outdir / f"mic_raw_{tag}.wav", result.mic_raw)
    _write_wav_mono_16k(outdir / f"speaker_ref_{tag}.wav", result.speaker_ref)
    _write_wav_mono_16k(outdir / f"mic_after_aec_{tag}.wav", result.mic_after_aec)
    with open(outdir / f"report_{tag}.json", "w", encoding="utf-8") as f:
        json.dump(result.as_dict(), f, ensure_ascii=False, indent=2)

    print(f"[AEC-POC] {tag}: "
          f"xcorr_lag={result.xcorr_lag_ms}ms  "
          f"metric_window=[{result.metric_start_ms},{result.metric_end_ms}]ms  "
          f"rms_raw_echo={result.rms_raw_echo_only:.5f}  "
          f"rms_aec_echo={result.rms_aec_echo_only:.5f}  "
          f"att_echo={result.attenuation_echo_only_db:.2f} dB  "
          f"xcorr_peak={result.xcorr_peak:.3f}  "
          f"RTF={result.rtf:.1f}x", flush=True)
    print(f"[AEC-POC] saved: {outdir}/{tag}.[wav,json]", flush=True)
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="AEC POC (pywebrtc-audio)")
    p.add_argument("--list", action="store_true", help="список устройств и выход")
    p.add_argument("--input", type=int, default=None, help="ID input device")
    p.add_argument("--output", type=int, default=None, help="ID output device")
    p.add_argument("--test", choices=["a", "b"], default="a",
                   help="a — только динамик, человек молчит; "
                        "b — динамик + человек говорит в микрофон")

    p.add_argument("--reference", type=str, default=None,
                   help="путь к WAV (16k/mono желательно; иначе ресемплим). "
                        "Если не задан — синтетический chirp.")
    p.add_argument("--signal-start-ms", type=int, default=DEFAULT_SIGNAL_START_MS,
                   help="начало активного окна reference (мс)")
    p.add_argument("--signal-end-ms", type=int, default=DEFAULT_SIGNAL_END_MS,
                   help="конец активного окна reference (мс)")

    # Две независимые задержки.
    p.add_argument("--far-offset-ms", type=int, default=0,
                   help="сдвиг reference относительно mic в нашей модели. "
                        "По умолчанию 0 — AEC сам оценивает задержку. "
                        "НЕ влияет на metric window.")
    p.add_argument("--stream-delay-ms", type=int, default=0,
                   help="hint для AudioProcessor(stream_delay_ms=...). "
                        "По умолчанию 0 — AEC3 использует внутреннюю оценку. "
                        "НЕ влияет на metric window.")

    # Sweep'ы (по умолчанию выключены).
    p.add_argument("--far-offset-sweep", type=str, default=None,
                   help="перебор far-offset в мс, например 0,20,40,60")
    p.add_argument("--stream-delay-sweep", type=str, default=None,
                   help="перебор stream-delay в мс, например 0,20,40,60")

    p.add_argument("--volume", type=float, default=1.0,
                   help="множитель амплитуды PCM reference в outdata")
    p.add_argument("--volume-sweep", type=str, default=None,
                   help="перебор громкостей, например 0.3,0.7,1.0")
    p.add_argument("--blocksize", type=int, default=BLOCKSIZE,
                   help=f"размер блока в сэмплах (default {BLOCKSIZE} = 10 ms)")
    p.add_argument("--echo-tail-ms", type=int, default=DEFAULT_ECHO_TAIL_MS,
                   help="сколько ещё писать mic после конца reference")
    p.add_argument("--outdir", type=str, default=None,
                   help="куда сохранять WAV/JSON (по умолчанию tools/aec_poc_out)")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    if args.list:
        print_devices()
        return 0

    outdir = Path(args.outdir) if args.outdir else Path(__file__).parent / "aec_poc_out"

    # Reference.
    if args.reference:
        p = Path(args.reference)
        if not p.is_file():
            print(f"[AEC-POC] reference не найден: {p}", flush=True)
            return 2
        print(f"[AEC-POC] reference WAV: {p}", flush=True)
        reference = load_reference_wav(
            p,
            signal_start_ms=args.signal_start_ms,
            signal_end_ms=args.signal_end_ms,
        )
    else:
        print("[AEC-POC] reference: синтетический chirp "
              f"(head={REF_SILENCE_HEAD_SEC}s, sig={REF_SIGNAL_SEC}s, "
              f"tail={REF_SILENCE_TAIL_SEC}s)", flush=True)
        reference = make_synthetic_reference()

    ref_sec = len(reference) / SAMPLE_RATE
    print(f"[AEC-POC] reference length={len(reference)} samples ({ref_sec:.3f}s)", flush=True)
    print(f"[AEC-POC] ref signal window: "
          f"[{args.signal_start_ms}, {args.signal_end_ms}] ms", flush=True)

    # Sweep'ы.
    far_offsets = ([int(x.strip()) for x in args.far_offset_sweep.split(",") if x.strip()]
                   if args.far_offset_sweep else [args.far_offset_ms])
    stream_delays = ([int(x.strip()) for x in args.stream_delay_sweep.split(",") if x.strip()]
                     if args.stream_delay_sweep else [args.stream_delay_ms])
    volumes = ([float(x.strip()) for x in args.volume_sweep.split(",") if x.strip()]
               if args.volume_sweep else [args.volume])

    if args.test == "a":
        print("\n[AEC-POC] TEST A: только динамик. Человек должен молчать.", flush=True)
    else:
        print("\n[AEC-POC] TEST B: динамик + человек. Говорите в микрофон.",
              flush=True)

    results: list[AecRunResult] = []
    for v in volumes:
        for fo in far_offsets:
            for sd_ms in stream_delays:
                try:
                    r = run_one(
                        reference=reference,
                        input_device=args.input,
                        output_device=args.output,
                        far_offset_ms=fo,
                        stream_delay_ms=sd_ms,
                        volume=v,
                        test=args.test,
                        outdir=outdir,
                        blocksize=args.blocksize,
                        echo_tail_ms=args.echo_tail_ms,
                        ref_signal_start_ms=args.signal_start_ms,
                        ref_signal_end_ms=args.signal_end_ms,
                    )
                    results.append(r)
                except Exception as e:  # noqa: BLE001
                    print(f"[AEC-POC] far_offset={fo} stream_delay={sd_ms} "
                          f"volume={v} FAILED: {e}", flush=True)

    if results:
        print("\n[AEC-POC] === SUMMARY ===", flush=True)
        print(f"  {'test':>4} {'far_off':>7} {'strm_dly':>8} {'vol':>5} "
              f"{'xcorr_lag':>9} {'metric_win':>15} "
              f"{'rms_raw_e':>10} {'rms_aec_e':>10} {'att_e_db':>9} "
              f"{'xcorr_pk':>8} {'RTF':>6}", flush=True)
        for r in results:
            win = f"[{r.metric_start_ms},{r.metric_end_ms}]"
            print(f"  {r.test:>4} {r.far_offset_ms:>7} {r.stream_delay_ms:>8} "
                  f"{r.volume:>5.2f} {r.xcorr_lag_ms:>9} {win:>15} "
                  f"{r.rms_raw_echo_only:>10.5f} {r.rms_aec_echo_only:>10.5f} "
                  f"{r.attenuation_echo_only_db:>9.2f} "
                  f"{r.xcorr_peak:>8.3f} "
                  f"{r.rtf:>6.1f}", flush=True)
        print(f"\n[AEC-POC] WAV+JSON: {outdir}", flush=True)
        print("[AEC-POC] Прослушайте mic_raw_*.wav и mic_after_aec_*.wav вручную.",
              flush=True)
        print("[AEC-POC] Тест A: эхо должно быть подавлено.", flush=True)
        print("[AEC-POC] Тест B: человеческая речь должна остаться.", flush=True)
        print("[AEC-POC] xcorr_lag_ms — ИЗМЕРЕННАЯ акустическая задержка "
              "(reference vs mic), по ней сдвинуто metric-окно. "
              "far_offset_ms и stream_delay_ms — параметры алгоритма, "
              "не физическая задержка.", flush=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
