"""
Тесты валидаторов Actions: GradeStudent, OpenPresentation, OpenVideo, NextSlide.

Запуск через pytest:
    pytest -v tools/test_validators.py
Прямой запуск:
    python -m tools.test_validators
"""
import sys

from assistant.actions.base import ActionContext
from assistant.actions.validators import (
    GradeStudentValidator,
    OpenPresentationValidator,
    OpenVideoValidator,
    NextSlideValidator,
)
from assistant.intent.base import Intent


# --- helpers ---

def _ctx_offline():
    """Контекст без gradebook — типичный случай для проверок допустимости."""
    return ActionContext(
        addressed_to_assistant=True,
        gradebook=None,
        dry_run=True,
    )


def _ctx_no_address():
    return ActionContext(addressed_to_assistant=False)


# --- GradeStudentValidator ---

def test_grade_student_rejects_not_addressed():
    v = GradeStudentValidator()
    intent = Intent(name="grade_student",
                    params={"student": "Сидорову", "grade": 2},
                    confidence=0.9)
    r = v.validate(intent, _ctx_no_address())
    assert r.allowed is False
    assert "не адресована" in r.reason.lower()


def test_grade_student_rejects_low_confidence():
    v = GradeStudentValidator()
    intent = Intent(name="grade_student",
                    params={"student": "Сидорову", "grade": 2},
                    confidence=0.3)
    r = v.validate(intent, _ctx_offline())
    assert r.allowed is False
    assert "уверенность" in r.reason.lower() or "низкая" in r.reason.lower()


def test_grade_student_rejects_missing_student():
    v = GradeStudentValidator()
    intent = Intent(name="grade_student",
                    params={"grade": 2},
                    confidence=0.9)
    r = v.validate(intent, _ctx_offline())
    assert r.allowed is False
    assert "student" in r.missing


def test_grade_student_rejects_invalid_grade():
    v = GradeStudentValidator()
    intent = Intent(name="grade_student",
                    params={"student": "Сидорову", "grade": 1},
                    confidence=0.9)
    r = v.validate(intent, _ctx_offline())
    assert r.allowed is False
    assert "grade" in r.missing


def test_grade_student_rejects_grade_6():
    v = GradeStudentValidator()
    intent = Intent(name="grade_student",
                    params={"student": "Сидорову", "grade": 6},
                    confidence=0.9)
    r = v.validate(intent, _ctx_offline())
    assert r.allowed is False


def test_grade_student_without_gradebook_reports_clarification():
    v = GradeStudentValidator()
    intent = Intent(name="grade_student",
                    params={"student": "Сидорову", "grade": 3},
                    confidence=0.95)
    r = v.validate(intent, _ctx_offline())
    assert r.allowed is False
    # Точный текст может отличаться, но пользователь должен получить
    # понятное объяснение — оно уходит в clarification или reason.
    explanation = (r.clarification or r.reason).lower()
    assert "журнал" in explanation


# --- OpenPresentationValidator ---

def test_open_presentation_accepts_valid():
    v = OpenPresentationValidator()
    intent = Intent(name="open_presentation",
                    params={"topic": "физика"},
                    confidence=0.9)
    r = v.validate(intent, _ctx_offline())
    assert r.allowed is True


def test_open_presentation_rejects_not_addressed():
    v = OpenPresentationValidator()
    intent = Intent(name="open_presentation",
                    params={"topic": "физика"},
                    confidence=0.9)
    r = v.validate(intent, _ctx_no_address())
    assert r.allowed is False


def test_open_presentation_rejects_low_confidence():
    v = OpenPresentationValidator()
    intent = Intent(name="open_presentation",
                    params={"topic": "физика"},
                    confidence=0.1)
    r = v.validate(intent, _ctx_offline())
    assert r.allowed is False


# --- OpenVideoValidator ---

def test_open_video_accepts_valid():
    v = OpenVideoValidator()
    intent = Intent(name="open_video",
                    params={"topic": "электричество"},
                    confidence=0.9)
    r = v.validate(intent, _ctx_offline())
    assert r.allowed is True


def test_open_video_rejects_not_addressed():
    v = OpenVideoValidator()
    intent = Intent(name="open_video",
                    params={"topic": "электричество"},
                    confidence=0.9)
    r = v.validate(intent, _ctx_no_address())
    assert r.allowed is False


def test_open_video_rejects_low_confidence():
    v = OpenVideoValidator()
    intent = Intent(name="open_video",
                    params={"topic": "x"},
                    confidence=0.1)
    r = v.validate(intent, _ctx_offline())
    assert r.allowed is False


# --- NextSlideValidator ---

def test_next_slide_accepts_valid():
    v = NextSlideValidator()
    intent = Intent(name="next_slide", params={}, confidence=0.95)
    r = v.validate(intent, _ctx_offline())
    assert r.allowed is True


def test_next_slide_rejects_not_addressed():
    v = NextSlideValidator()
    intent = Intent(name="next_slide", params={}, confidence=0.95)
    r = v.validate(intent, _ctx_no_address())
    assert r.allowed is False


def test_next_slide_rejects_low_confidence():
    v = NextSlideValidator()
    intent = Intent(name="next_slide", params={}, confidence=0.5)
    r = v.validate(intent, _ctx_offline())
    assert r.allowed is False


# --- run_all ---

def run_all():
    tests = [
        test_grade_student_rejects_not_addressed,
        test_grade_student_rejects_low_confidence,
        test_grade_student_rejects_missing_student,
        test_grade_student_rejects_invalid_grade,
        test_grade_student_rejects_grade_6,
        test_grade_student_without_gradebook_reports_clarification,
        test_open_presentation_accepts_valid,
        test_open_presentation_rejects_not_addressed,
        test_open_presentation_rejects_low_confidence,
        test_open_video_accepts_valid,
        test_open_video_rejects_not_addressed,
        test_open_video_rejects_low_confidence,
        test_next_slide_accepts_valid,
        test_next_slide_rejects_not_addressed,
        test_next_slide_rejects_low_confidence,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"[OK] {t.__name__}", flush=True)
        except AssertionError as e:
            failed += 1
            print(f"[FAIL] {t.__name__}: {e}", flush=True)
        except Exception as e:
            failed += 1
            print(f"[ERROR] {t.__name__}: {type(e).__name__}: {e}", flush=True)
    print(flush=True)
    print(f"=== {len(tests) - failed}/{len(tests)} VALIDATOR TESTS PASSED ===", flush=True)
    return failed


def main():
    import os
    if not os.path.exists("assistant"):
        print("Запускать из корня проекта.", flush=True)
        sys.exit(2)
    sys.exit(1 if run_all() else 0)


if __name__ == "__main__":
    main()
