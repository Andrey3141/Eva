"""
Единая точка определения путей EVA.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _frozen_base() -> Path:
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    return Path(sys.executable).resolve().parent


def _source_base() -> Path:
    return Path(__file__).resolve().parent.parent


def is_frozen() -> bool:
    return _is_frozen()


def runtime_kind() -> str:
    return "pyinstaller" if _is_frozen() else "source"


def base_dir() -> Path:
    return _frozen_base() if _is_frozen() else _source_base()


def project_root() -> Path:
    if _is_frozen():
        return Path(sys.executable).resolve().parent
    return _source_base()


def user_data_dir() -> Path:
    if sys.platform.startswith("win"):
        root = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(root) / "EVA"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "EVA"
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg) / "EVA"
    return Path.home() / ".local" / "share" / "EVA"


def user_cache_dir() -> Path:
    if sys.platform.startswith("win"):
        root = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(root) / "EVA" / "Cache"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "EVA"
    xdg = os.environ.get("XDG_CACHE_HOME")
    if xdg:
        return Path(xdg) / "EVA"
    return Path.home() / ".cache" / "EVA"


def temp_dir() -> Path:
    import tempfile
    return Path(tempfile.gettempdir())


def env_path(name: str, default: str) -> Path:
    raw = os.environ.get(name, "").strip()
    if not raw:
        raw = default
    p = Path(raw).expanduser()
    if not p.is_absolute():
        p = base_dir() / p
    return p


def env_file_path() -> Path | None:
    candidates = [
        user_data_dir() / ".env",
        base_dir() / ".env",
    ]
    for c in candidates:
        try:
            if c.is_file():
                return c
        except OSError:
            continue
    return None


def silero_model_path() -> Path:
    return env_path("SILERO_MODEL_PATH", "assets/silero/v4_ru.pt")


def avatar_dir() -> Path:
    return env_path("AVATAR_DIR", "assets/avatar")


def gradebook_path() -> Path:
    return env_path("GRADEBOOK_PATH", "data/test_gradebook.xlsx")


def whisper_cache_dir() -> Path:
    p = env_path("WHISPER_CACHE_DIR", str(user_cache_dir() / "whisper"))
    try:
        p.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return p


def logs_dir() -> Path:
    p = env_path("EVA_LOG_DIR", str(user_data_dir() / "logs"))
    try:
        p.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return p


def fastembed_cache_dir() -> Path:
    p = env_path("EVA_FASTEMBED_CACHE_DIR", str(user_cache_dir() / "fastembed"))
    try:
        p.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return p


def settings_path() -> Path:
    return user_data_dir() / "settings.json"


# --- assets ---

def assets_dir() -> Path:
    return env_path("EVA_ASSETS_DIR", "assets")


# --- avatar media ---

def preview_video_path() -> Path:
    """Стартовый preview. Не зацикливается."""
    return avatar_dir() / "preview.mp4"


def warp_video_path() -> Path:
    """Базовое состояние аватара. Зацикливается."""
    return avatar_dir() / "warp.mp4"


def speaks_video_path() -> Path:
    """Состояние SPEAKING. Зацикливается. Может отсутствовать."""
    return avatar_dir() / "speaks.mp4"


def thinks_video_path() -> Path:
    """Состояние THINKING. Зацикливается. Может отсутствовать."""
    return avatar_dir() / "thinks.mp4"


# --- deprecated wrappers (не используются новой логикой) ---

def warp_gif_path() -> Path:
    """
    DEPRECATED: старый GIF-аватар. Оставлен только для совместимости
    с тестами старого формата. В production не используется.
    """
    return env_path("EVA_WARP_PATH", "assets/warp.gif")


def preview_video_path_legacy() -> Path:
    """DEPRECATED: старый путь assets/preview.mp4."""
    return env_path("EVA_PREVIEW_PATH", "assets/preview.mp4")


# --- presentations ---

def _desktop_dir() -> Path:
    if sys.platform.startswith("win"):
        try:
            import ctypes
            from ctypes import wintypes
            CSIDL_DESKTOPDIRECTORY = 0x0010
            buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
            ctypes.windll.shell32.SHGetFolderPathW(
                None, CSIDL_DESKTOPDIRECTORY, None, 0, buf
            )
            if buf.value:
                return Path(buf.value)
        except Exception:
            pass
        home = os.environ.get("USERPROFILE") or str(Path.home())
        return Path(home) / "Desktop"

    if sys.platform == "darwin":
        return Path.home() / "Desktop"

    xdg = os.environ.get("XDG_DESKTOP_DIR")
    if xdg:
        return Path(xdg).expanduser()

    xdg_config = Path.home() / ".config" / "user-dirs.dirs"
    if xdg_config.is_file():
        try:
            for line in xdg_config.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("XDG_DESKTOP_DIR="):
                    _, _, val = line.partition("=")
                    val = val.strip().strip('"')
                    val = val.replace("$HOME", str(Path.home()))
                    if val:
                        return Path(val).expanduser()
        except Exception:
            pass

    return Path.home() / "Desktop"


def default_presentations_dir() -> Path:
    return _desktop_dir() / "Презентации EVA"


def presentations_dir() -> Path:
    p = env_path("PRESENTATIONS_DIR", str(default_presentations_dir()))
    try:
        p.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return p


def describe() -> str:
    env_path_ = env_file_path()
    return (
        f"[PATHS] Runtime: {runtime_kind()}\n"
        f"[PATHS] Base:    {base_dir()}\n"
        f"[PATHS] Project: {project_root()}\n"
        f"[PATHS] Data:    {user_data_dir()}\n"
        f"[PATHS] Cache:   {user_cache_dir()}\n"
        f"[PATHS] Logs:    {logs_dir()}\n"
        f"[PATHS] Settings:{settings_path()}\n"
        f"[PATHS] .env:    {env_path_ if env_path_ else '<not found>'}\n"
        f"[PATHS] Silero:  {silero_model_path()}\n"
        f"[PATHS] Avatar:  {avatar_dir()}\n"
        f"[PATHS] Preview: {preview_video_path()}\n"
        f"[PATHS] Warp:    {warp_video_path()}\n"
        f"[PATHS] Speaks:  {speaks_video_path()}\n"
        f"[PATHS] Thinks:  {thinks_video_path()}\n"
        f"[PATHS] Whisper: {whisper_cache_dir()}\n"
        f"[PATHS] FastEmbed: {fastembed_cache_dir()}\n"
        f"[PATHS] Presentations: {presentations_dir()}"
    )
