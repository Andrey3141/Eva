"""
Тесты IntentFusion — только чистая логика, без зависимостей.

Правила:
  1. Согласие → intent с повышенной уверенностью.
  2. Один конкретный, второй пустой → берём конкретный, если ≥ min_individual.
  3. Конфликт двух конкретных → intent=None (LLM fallback).
  4. Оба пустые → intent=None.
"""
import pytest

from assistant.intent.router.fusion import IntentFusion
from assistant.intent.router.types import IntentPrediction


def _pred(intent, conf, source="test"):
    return IntentPrediction(intent=intent, confidence=conf, source=source)


# --- 1. Согласие ---

def test_agreement_high_confidence():
    fusion = IntentFusion()
    r = fusion.fuse(
        _pred("open_video", 0.91),
        _pred("open_video", 0.96),
    )
    assert r.intent == "open_video"
    assert r.agree is True
    # max(0.91, 0.96) + 0.05 = 1.01 → cap to 1.0
    assert r.confidence == pytest.approx(1.0, abs=1e-6)


def test_agreement_medium_confidence():
    fusion = IntentFusion()
    r = fusion.fuse(
        _pred("open_video", 0.6),
        _pred("open_video", 0.7),
    )
    assert r.intent == "open_video"
    assert r.agree is True
    assert r.confidence == pytest.approx(0.75, abs=1e-6)


# --- 2. Один конкретный, второй пустой ---

def test_one_concrete_one_empty_high_confidence():
    fusion = IntentFusion()
    r = fusion.fuse(
        _pred("open_video", 0.9),
        _pred("", 0.0),
    )
    assert r.intent == "open_video"
    assert r.agree is False
    assert r.confidence == pytest.approx(0.9, abs=1e-6)


def test_one_concrete_one_empty_low_confidence():
    fusion = IntentFusion()
    r = fusion.fuse(
        _pred("open_video", 0.4),
        _pred("", 0.0),
    )
    # 0.4 < min_individual (0.55) → не уверены.
    assert r.intent is None


# --- 3. Конфликт двух конкретных ---

def test_disagreement_both_medium():
    fusion = IntentFusion()
    r = fusion.fuse(
        _pred("open_video", 0.55),
        _pred("answer", 0.61),
    )
    assert r.intent is None
    assert r.agree is False


def test_disagreement_one_dominant_returns_none():
    """
    Даже если один сильно увереннее — при конфликте двух конкретных
    fusion не выбирает победителя. Решение уходит в LLM.
    """
    fusion = IntentFusion()
    r = fusion.fuse(
        _pred("open_video", 0.91),
        _pred("answer", 0.4),
    )
    assert r.intent is None
    assert r.agree is False


def test_disagreement_high_both_returns_none():
    fusion = IntentFusion()
    r = fusion.fuse(
        _pred("open_video", 0.95),
        _pred("answer", 0.90),
    )
    assert r.intent is None
    assert r.agree is False


def test_disagreement_embedding_full_ml_half():
    """
    Точный сценарий из ТЗ:
      embedding = open_video 1.0
      ML        = answer     0.5
    → Fusion.intent = None → LLM fallback.
    """
    fusion = IntentFusion()
    r = fusion.fuse(
        _pred("open_video", 1.0),
        _pred("answer", 0.5),
    )
    assert r.intent is None
    assert r.agree is False


# --- 4. Оба пустые ---

def test_both_empty():
    fusion = IntentFusion()
    r = fusion.fuse(_pred("", 0.0), _pred("", 0.0))
    assert r.intent is None
    assert r.confidence == 0.0


def test_both_low_confidence():
    fusion = IntentFusion()
    r = fusion.fuse(
        _pred("", 0.3),
        _pred("", 0.2),
    )
    assert r.intent is None
    assert r.agree is False


def test_both_below_min_individual_concrete():
    """
    Даже если оба вернули конкретные, но разные — конфликт → None.
    Если один вернул конкретный, но ниже порога — тоже None.
    """
    fusion = IntentFusion()
    r = fusion.fuse(
        _pred("open_video", 0.3),
        _pred("answer", 0.2),
    )
    assert r.intent is None
