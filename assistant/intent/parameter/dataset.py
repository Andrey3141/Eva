"""
Загрузка датасета для MLSlotTagger.

Формат — data/parameter_examples.json (см. файл).
Кэшируется по пути, поддерживает переопределение через env
EVA_PARAMETER_EXAMPLES.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from assistant import paths


_CACHE: Optional[list[dict]] = None


def default_examples_path() -> Path:
    override = os.getenv("EVA_PARAMETER_EXAMPLES", "").strip()
    if override:
        p = Path(override).expanduser()
        if not p.is_absolute():
            p = paths.base_dir() / p
        return p
    return paths.base_dir() / "data" / "parameter_examples.json"


def load_parameter_examples(path: Optional[Path] = None) -> list[dict]:
    """
    Возвращает список размеченных примеров. Каждый — dict
    с ключами: intent, text, tokens (список [token, role]).
    """
    global _CACHE
    if path is None and _CACHE is not None:
        return _CACHE

    target = Path(path) if path is not None else default_examples_path()
    if not target.is_file():
        return []

    try:
        raw = target.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError):
        return []

    if not isinstance(data, dict):
        return []
    examples = data.get("examples")
    if not isinstance(examples, list):
        return []

    cleaned: list[dict] = []
    for ex in examples:
        if not isinstance(ex, dict):
            continue
        intent = str(ex.get("intent") or "").strip()
        text = str(ex.get("text") or "").strip()
        tokens = ex.get("tokens")
        if not intent or not text or not isinstance(tokens, list):
            continue
        cleaned_tokens: list[tuple[str, str]] = []
        for t in tokens:
            if isinstance(t, list) and len(t) == 2:
                cleaned_tokens.append((str(t[0]), str(t[1])))
        if cleaned_tokens:
            cleaned.append({
                "intent": intent,
                "text": text,
                "tokens": cleaned_tokens,
            })

    if path is None:
        _CACHE = cleaned
    return cleaned


def clear_cache() -> None:
    global _CACHE
    _CACHE = None
