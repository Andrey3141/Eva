"""
Пользовательские настройки EVA.

Хранятся в paths.settings_path() (user_data_dir()/settings.json).
API-ключи здесь не сохраняются — они остаются в .env.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Optional

from assistant import paths


UI_EDITABLE_KEYS: tuple[str, ...] = (
    "ASSISTANT_NAME",
    "ASSISTANT_ALIASES",
    "WHISPER_MODEL",
    "WHISPER_LANGUAGE",
    "TTS_PROVIDER",
    "SILERO_SPEAKER",
    "LLM_PROVIDER",
    "GEMINI_MODEL",
    "GROQ_MODEL",
    "CEREBRAS_MODEL",
    "OPENROUTER_MODEL",
    "DEEPSEEK_MODEL",
    "UI_ANIMATIONS_ENABLED",
    "UI_VOLUME",
    "UI_SPEECH_RATE",
    "INPUT_DEVICE_INDEX",
    "PRESENTATIONS_DIR",
    "GRADEBOOK_PATH",
    "PRESENTATION_MATCH_THRESHOLD",
    "PRESENTATION_AMBIGUITY_MARGIN",
    "PARAMETER_ROUTER_MODE",
)


class SettingsStore:
    def __init__(self, path: Optional[Path] = None, bus=None):
        self.path = Path(path) if path else paths.settings_path()
        self._lock = threading.Lock()
        self._data: dict[str, Any] = {}
        self._bus = bus
        self._load()

    def _load(self) -> None:
        if not self.path.is_file():
            self._data = {}
            return
        try:
            raw = self.path.read_text(encoding="utf-8")
            data = json.loads(raw)
            if isinstance(data, dict):
                self._data = {k: v for k, v in data.items() if k in UI_EDITABLE_KEYS}
            else:
                self._data = {}
        except (OSError, json.JSONDecodeError):
            self._data = {}

    def has(self, key: str) -> bool:
        return key in self._data

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        if key not in UI_EDITABLE_KEYS:
            raise KeyError(f"Ключ '{key}' не разрешён для пользовательских настроек.")
        self._data[key] = value

    def as_dict(self) -> dict[str, Any]:
        return dict(self._data)

    def save(self) -> None:
        with self._lock:
            tmp = self.path.with_suffix(".json.tmp")
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = json.dumps(self._data, ensure_ascii=False, indent=2)
            tmp.write_text(payload, encoding="utf-8")
            tmp.replace(self.path)

    def save_from(self, data: dict[str, Any]) -> None:
        cleaned: dict[str, Any] = {}
        for k, v in data.items():
            if k not in UI_EDITABLE_KEYS:
                continue
            if k == "ASSISTANT_ALIASES":
                cleaned[k] = v if v is not None else ""
                continue
            if v in (None, ""):
                continue
            cleaned[k] = v

        with self._lock:
            self._data = cleaned
            tmp = self.path.with_suffix(".json.tmp")
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = json.dumps(self._data, ensure_ascii=False, indent=2)
            tmp.write_text(payload, encoding="utf-8")
            tmp.replace(self.path)

        self.apply_to_config()
        self._publish_changed(list(cleaned.keys()))

    def apply_to_config(self) -> None:
        from config import Config
        Config.apply_store(self)

    def _publish_changed(self, changed_keys: list[str]) -> None:
        if self._bus is None:
            return
        try:
            from assistant.events import Event, EventType
            self._bus.publish(Event(
                type=EventType.CONFIG_CHANGED,
                payload={"changed_keys": list(changed_keys)},
            ))
        except Exception as e:
            print(f"[SettingsStore] CONFIG_CHANGED publish error: {e}", flush=True)
