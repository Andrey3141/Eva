"""
Тесты MLIntentClassifier (TF-IDF + LogisticRegression).
Пропускаются, если sklearn не установлен.
"""
import pytest

sklearn = pytest.importorskip("sklearn")

from assistant.intent.router.ml_classifier import MLIntentClassifier


@pytest.fixture
def examples():
    return {
        "open_video": [
            "включи видео", "покажи видео", "запусти видео",
            "включи ролик", "покажи ролик",
        ],
        "open_presentation": [
            "открой презентацию", "покажи презентацию",
            "открой слайды", "покажи слайды",
        ],
        "grade_student": [
            "поставь Иванову четыре", "поставь Сидорову три",
            "Иванов пять", "Сидоров два",
        ],
        "answer": [
            "привет", "как дела", "сколько будет два плюс два",
            "расскажи про трансформаторы",
        ],
    }


def test_predict_obvious_case(examples):
    clf = MLIntentClassifier(examples)
    pred = clf.predict("включи видео")
    assert pred.intent == "open_video"
    assert pred.confidence > 0.0
    assert pred.source == "ml"


def test_predict_unknown_text_is_low_confidence(examples):
    clf = MLIntentClassifier(examples)
    pred = clf.predict("абракадабра зют фыр")
    # Не должно уверенно попасть в известный intent.
    assert pred.confidence < 0.9


def test_predict_empty_text(examples):
    clf = MLIntentClassifier(examples)
    pred = clf.predict("")
    assert pred.intent == ""
    assert pred.confidence == 0.0


def test_no_examples_returns_empty():
    clf = MLIntentClassifier({})
    pred = clf.predict("включи видео")
    assert pred.intent == ""
    assert pred.confidence == 0.0


def test_single_class_returns_empty():
    clf = MLIntentClassifier({"answer": ["привет", "как дела"]})
    pred = clf.predict("привет")
    assert pred.intent == ""
    assert pred.confidence == 0.0
