"""
Загрузка датасета intent'ов из JSON.

Датасет отделён от кода: примеры можно добавлять, не трогая Python.
Файл по умолчанию: data/intent_examples.json.
Путь можно переопределить env-переменной EVA_INTENT_EXAMPLES.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from assistant import paths


_CACHE: Optional[dict[str, list[str]]] = None


def default_examples_path() -> Path:
    override = os.getenv("EVA_INTENT_EXAMPLES", "").strip()
    if override:
        p = Path(override).expanduser()
        if not p.is_absolute():
            p = paths.base_dir() / p
        return p
    return paths.base_dir() / "data" / "intent_examples.json"


def load_intent_examples(path: Optional[Path] = None) -> dict[str, list[str]]:
    """
    Загружает датасет intent → list[str] примеров.

    Кэширует результат по пути. Возвращает пустой dict, если файл
    отсутствует или повреждён (Router должен уметь работать без датасета).
    """
    global _CACHE
    if path is None and _CACHE is not None:
        return _CACHE

    target = Path(path) if path is not None else default_examples_path()
    if not target.is_file():
        return {} if path is not None else {}

    try:
        raw = target.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError):
        return {}

    if not isinstance(data, dict):
        return {}

    cleaned: dict[str, list[str]] = {}
    for intent, examples in data.items():
        if not isinstance(intent, str) or not intent:
            continue
        if not isinstance(examples, list):
            continue
        items = [str(x).strip() for x in examples if str(x).strip()]
        if items:
            cleaned[intent] = items

    if path is None:
        _CACHE = cleaned
    return cleaned


def clear_cache() -> None:
    global _CACHE
    _CACHE = None
