"""
Кроссплатформенное воспроизведение аудиофайлов.
  - Windows: winsound.PlaySound для WAV; для MP3 — ffplay/mpv, если есть,
             иначе попытка через winsound (не сработает для MP3).
  - Linux:   aplay / paplay / ffplay.
  - macOS:   afplay.
Не тянет тяжёлых зависимостей.
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
from pathlib import Path


def _which(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def play_wav(path: str | Path) -> None:
    path = str(path)
    system = platform.system()

    if system == "Windows":
        # winsound — часть stdlib, работает с WAV.
        try:
            import winsound
            winsound.PlaySound(path, winsound.SND_FILENAME)
            return
        except Exception:
            # Fallback на плеер, если есть.
            for cmd in ("ffplay", "mpv", "vlc"):
                if _which(cmd):
                    if cmd == "ffplay":
                        subprocess.run(
                            [cmd, "-nodisp", "-autoexit", "-loglevel", "quiet", path],
                            check=False,
                        )
                    elif cmd == "mpv":
                        subprocess.run(
                            [cmd, "--no-video", "--really-quiet", path],
                            check=False,
                        )
                    else:  # vlc
                        subprocess.run([cmd, "--play-and-exit", path], check=False)
                    return
            raise RuntimeError("Не найден способ воспроизвести WAV на Windows")

    if system == "Darwin":
        subprocess.run(["afplay", path], check=False)
        return

    # Linux / другие UNIX
    for cmd in (["aplay", "-q"], ["paplay"], ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet"]):
        if _which(cmd[0]):
            subprocess.run(
                cmd + [path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            return
    raise RuntimeError("Не найден аудиоплеер для WAV (aplay/paplay/ffplay)")


def play_mp3(path: str | Path) -> None:
    path = str(path)
    system = platform.system()

    if system == "Windows":
        # winsound не умеет MP3. Пробуем ffplay/mpv/vlc.
        for cmd in ("ffplay", "mpv", "vlc"):
            if _which(cmd):
                if cmd == "ffplay":
                    subprocess.run(
                        [cmd, "-nodisp", "-autoexit", "-loglevel", "quiet", path],
                        check=False,
                    )
                elif cmd == "mpv":
                    subprocess.run([cmd, "--no-video", "--really-quiet", path], check=False)
                else:
                    subprocess.run([cmd, "--play-and-exit", path], check=False)
                return
        # Совсем без вариантов — осмысленная ошибка.
        raise RuntimeError(
            "Для MP3 на Windows нужен ffplay/mpv/vlc в PATH. "
            "Либо используйте TTS_PROVIDER=pyttsx3 / Silero (WAV)."
        )

    if system == "Darwin":
        subprocess.run(["afplay", path], check=False)
        return

    for cmd in (["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet"], ["mpg123", "-q"], ["mpv", "--no-video", "--really-quiet"]):
        if _which(cmd[0]):
            subprocess.run(
                cmd + [path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            return
    raise RuntimeError("Не найден аудиоплеер для MP3 (ffplay/mpg123/mpv)")


def play(path: str | Path) -> None:
    p = Path(path)
    ext = p.suffix.lower()
    if ext == ".wav":
        play_wav(p)
    elif ext in (".mp3", ".m4a", ".aac", ".ogg"):
        play_mp3(p)
    else:
        # По умолчанию пробуем как WAV.
        play_wav(p)
