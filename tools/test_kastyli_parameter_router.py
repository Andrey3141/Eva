"""
Тесты fallback-режима «кастыли».
"""
import sys

import pytest

from кастыли import КастылиParameterRouter


@pytest.fixture
def router():
    return КастылиParameterRouter()


def _extract(router, text, intent_name):
    params, _a, _r, _d = router.extract_params(text, intent_name)
    return params


# --- presentations ---

@pytest.mark.parametrize("text,expected", [
    ("открой презентацию итоговое занятие", "итоговое занятие"),
    ("открой презентацию по охране труда", "по охране труда"),
    ("открой презентацию трансформаторы", "трансформаторы"),
])
def test_presentation_topic(router, text, expected):
    params = _extract(router, text, "open_presentation")
    assert params.get("topic") == expected


def test_presentation_no_topic(router):
    params = _extract(router, "открой презентацию", "open_presentation")
    assert params == {}


# --- video ---

def test_video_topic(router):
    params = _extract(
        router,
        "открой видео руководство по эксплуатации Кассового аппарата Titan Plus",
        "open_video",
    )
    assert params.get("topic") == \
        "руководство по эксплуатации Кассового аппарата Titan Plus"


def test_video_rolik(router):
    params = _extract(router, "включи ролик про трансформаторы", "open_video")
    assert params.get("topic") == "про трансформаторы"


def test_video_no_topic(router):
    params = _extract(router, "открой видео", "open_video")
    assert params == {}


# --- grade ---

@pytest.mark.parametrize("text", [
    "поставь Иванову 2",
    "поставь Иванову два",
    "поставь Иванову два балла",
    "Иванову 2",
])
def test_grade_ivanovu(router, text):
    params = _extract(router, text, "grade_student")
    assert params.get("student") == "Иванову"
    assert params.get("grade") == 2


@pytest.mark.parametrize("text,expected_student,expected_grade", [
    ("поставь Сидорову 5", "Сидорову", 5),
    ("Петрову 4", "Петрову", 4),
    ("Кузнецову два", "Кузнецову", 2),
    ("поставь Морозову три балла", "Морозову", 3),
])
def test_grade_other_students(router, text, expected_student, expected_grade):
    params = _extract(router, text, "grade_student")
    assert params.get("student") == expected_student
    assert params.get("grade") == expected_grade


# --- service intents ---

def test_next_slide_no_params(router):
    params = _extract(router, "следующий слайд", "next_slide")
    assert params == {}


def test_answer_no_params(router):
    params = _extract(router, "привет", "answer")
    assert params == {}


def run_all():
    print("Запуск через pytest: "
          "pytest -v tools/test_kastyli_parameter_router.py", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(run_all())
