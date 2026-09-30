"""
Тесты маршрутизации close/restart-фраз через _structural_override.

Проверяют, что:
  «закрой презентацию» → close_presentation
  «закрой видео»       → close_video
  «закрой Excel»       → close_excel
  «закрой файл»        → close_file
  «переоткрой Excel»   → restart_excel
  «обнови презентацию» → restart_presentation
"""
import sys

import pytest

from assistant.intent.router.router import _structural_override


@pytest.mark.parametrize("text,expected", [
    ("закрой презентацию", "close_presentation"),
    ("закрой слайды", "close_presentation"),
    ("закрой видео", "close_video"),
    ("закрой ролик", "close_video"),
    ("закрой excel", "close_excel"),
    ("закрой таблицу", "close_excel"),
    ("закрой файл", "close_file"),
    ("закрой документ", "close_file"),
    ("переоткрой excel", "restart_excel"),
    ("обнови excel", "restart_excel"),
    ("перезапусти excel", "restart_excel"),
    ("переоткрой презентацию", "restart_presentation"),
    ("обнови презентацию", "restart_presentation"),
    ("перезапусти презентацию", "restart_presentation"),
])
def test_structural_override_close_restart(text, expected):
    assert _structural_override(text) == expected


@pytest.mark.parametrize("text,expected", [
    ("открой видео про трансформаторы", "open_video"),
    ("открой презентацию по физике", "open_presentation"),
    ("открой excel журнал", "open_excel"),
])
def test_structural_override_open(text, expected):
    assert _structural_override(text) == expected


def run_all():
    print("pytest -v tools/test_intent_routing_close_restart.py", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(run_all())
