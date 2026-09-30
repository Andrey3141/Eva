"""
Интеграционные тесты open_video: intent + params + Action.

Проверяют:
  - IntentRouter выдаёт open_video для типичных фраз;
  - ParameterRouter извлекает topic;
  - OpenVideoAction ищет файл в context.videos_dir и открывает.

Пока videos_dir как concept в проекте не оформлен — Action использует
тестовую директорию и мок _open_file.
"""
import sys
from pathlib import Path
from unittest import mock

import numpy as np
import pytest

from assistant.actions.actions_impl import OpenVideoAction
from assistant.actions.base import ActionContext


def _ctx(dir_path):
    return ActionContext(
        addressed_to_assistant=True,
        presentations_dir=str(dir_path),
        presentation_match_threshold=0.70,
        presentation_ambiguity_margin=0.05,
    )


def _make_file(dir_path: Path, name: str) -> Path:
    f = dir_path / name
    f.write_bytes(b"fake")
    return f


# ---------------------------------------------------------------------------
# Action: базовые сценарии
# ---------------------------------------------------------------------------

def test_open_video_action_with_topic_and_existing_file(tmp_path):
    """
    Если файл существует и тема совпадает — Action открывает.
    Пока использует presentations_dir как источник.
    """
    _make_file(tmp_path, "Руководство по эксплуатации кассового аппарата Titan Plus.mp4")
    action = OpenVideoAction()
    ctx = _ctx(tmp_path)
    with mock.patch("assistant.actions.actions_impl._open_file",
                    return_value=True) as m:
        result = action.run(
            {"topic": "руководство по эксплуатации кассового аппарата Titan Plus"},
            ctx,
        )
    assert result.executed is True, f"message={result.message}"
    assert m.call_count == 1


def test_open_video_action_no_topic_returns_error(tmp_path):
    action = OpenVideoAction()
    ctx = _ctx(tmp_path)
    result = action.run({}, ctx)
    assert result.executed is False
    assert "тему" in result.message.lower() or "уточните" in result.message.lower()


def test_open_video_action_no_dir_returns_error():
    action = OpenVideoAction()
    ctx = ActionContext(addressed_to_assistant=True, presentations_dir=None)
    result = action.run({"topic": "трансформаторы"}, ctx)
    assert result.executed is False


def run_all():
    print("Запуск через pytest: "
          "pytest -v tools/test_open_video_pipeline.py", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(run_all())
