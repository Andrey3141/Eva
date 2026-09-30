"""
Тесты загрузчика датасета data/intent_examples.json.
"""
import json
import os
import sys
from pathlib import Path

import pytest

from assistant.intent.router import dataset as dataset_mod
from assistant.intent.router.dataset import load_intent_examples


def test_default_path_points_to_data_dir():
    p = dataset_mod.default_examples_path()
    assert p.name == "intent_examples.json"
    assert "data" in str(p)


def test_load_real_dataset():
    examples = load_intent_examples()
    assert examples, "датасет не загружен"
    assert "open_video" in examples
    assert "open_presentation" in examples
    assert "grade_student" in examples
    assert "next_slide" in examples
    assert "answer" in examples
    for intent, phrases in examples.items():
        assert isinstance(phrases, list)
        assert len(phrases) >= 3, f"{intent}: мало примеров"


def test_load_missing_file_returns_empty(tmp_path):
    missing = tmp_path / "no_such.json"
    assert load_intent_examples(path=missing) == {}


def test_load_broken_json_returns_empty(tmp_path):
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    assert load_intent_examples(path=broken) == {}


def test_load_filters_bad_entries(tmp_path):
    p = tmp_path / "examples.json"
    p.write_text(json.dumps({
        "open_video": ["включи видео", "", "  ", "покажи видео"],
        "bad_intent": "not a list",
        "": ["empty intent"],
    }), encoding="utf-8")
    out = load_intent_examples(path=p)
    assert "open_video" in out
    assert out["open_video"] == ["включи видео", "покажи видео"]
    assert "bad_intent" not in out
    assert "" not in out
