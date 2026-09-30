from dataclasses import dataclass
from typing import Optional

import sounddevice as sd


@dataclass
class AudioInputInfo:
    index: int
    name: str
    channels: int
    default_samplerate: float
    hostapi: str
    is_monitor: bool
    is_default: bool


def _is_monitor_name(name: str) -> bool:
    """
    Эвристика: monitor — это петля вывода, не источник.
    На Linux/PulseAudio такие устройства обычно называются
    'Monitor of ...', 'monitor', '.monitor'.
    """
    if not name:
        return False
    low = name.lower()
    if "monitor" in low:
        return True
    if low.endswith(".monitor"):
        return True
    return False


def list_input_devices() -> list[AudioInputInfo]:
    devices = sd.query_devices()
    hostapis = sd.query_hostapis()

    result: list[AudioInputInfo] = []
    try:
        default_input_idx = sd.default.device[0]
    except Exception:
        default_input_idx = -1

    for idx, dev in enumerate(devices):
        max_in = int(dev.get("max_input_channels", 0) or 0)
        if max_in <= 0:
            continue
        hostapi_idx = int(dev.get("hostapi", 0) or 0)
        hostapi_name = hostapis[hostapi_idx]["name"] if hostapi_idx < len(hostapis) else "?"
        name = str(dev.get("name", "") or "")
        result.append(AudioInputInfo(
            index=idx,
            name=name,
            channels=max_in,
            default_samplerate=float(dev.get("default_samplerate", 0) or 0),
            hostapi=hostapi_name,
            is_monitor=_is_monitor_name(name),
            is_default=(idx == default_input_idx),
        ))
    return result


def _score_device(d: AudioInputInfo) -> int:
    """
    Чем выше — тем приоритетнее.
    Правила:
      - физический микрофон предпочтительнее monitor;
      - default system source — плюс;
      - 'analog-stereo' / 'analog-mono' / 'built-in' — плюс;
      - 'monitor' — большой минус.
    """
    score = 0
    low = d.name.lower()

    if d.is_monitor:
        score -= 1000

    if d.is_default:
        score += 50

    if "analog" in low:
        score += 30
    if "built-in" in low or "internal" in low:
        score += 20
    if "mic" in low or "microphone" in low:
        score += 15
    if "headset" in low or "headphone" in low:
        score += 5

    # чуть предпочитаем стерео/2-канальные (обычно у built-in)
    if d.channels >= 2:
        score += 2

    return score


def pick_input_device(prefer_index: Optional[int] = None) -> Optional[AudioInputInfo]:
    """
    Возвращает лучшее устройство ввода.
    Если prefer_index задан и это валидный input — вернуть его.
    Иначе — из списка физических (не monitor) выбрать с максимальным score.
    Если физических нет — вернуть None (не подсовываем monitor).
    """
    devices = list_input_devices()
    if not devices:
        return None

    if prefer_index is not None:
        for d in devices:
            if d.index == prefer_index:
                return d

    physical = [d for d in devices if not d.is_monitor]
    if not physical:
        return None

    physical.sort(key=_score_device, reverse=True)
    return physical[0]


def describe_device(d: Optional[AudioInputInfo]) -> str:
    if d is None:
        return "<none>"
    default_mark = " (default)" if d.is_default else ""
    monitor_mark = " [monitor]" if d.is_monitor else ""
    return (f"#{d.index} {d.name!r} · hostapi={d.hostapi} · "
            f"channels={d.channels} · sr={d.default_samplerate:.0f}"
            f"{default_mark}{monitor_mark}")
