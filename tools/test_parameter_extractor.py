"""
Тесты ParameterExtractor — локальное извлечение params.

Проверяют:
  - grade_student: student + grade из разных формулировок;
  - защита от математических фраз ("2 плюс 2" ≠ grade_student extraction);
  - open_video / open_presentation: topic из "про/по/о/об/на тему";
  - отсутствие topic → {} (не выдумывать);
  - next_slide, answer, unknown → {}.

Extractor НЕ меняет intent — тесты это тоже проверяют.
"""
import os
import sys

import pytest

from assistant.intent.router.parameter_extractor import ParameterExtractor


@pytest.fixture
def extractor():
    return ParameterExtractor()


# ---------------------------------------------------------------------------
# grade_student
# ---------------------------------------------------------------------------

def test_grade_ivanovu_4(extractor):
    params = extractor.extract("поставь Иванову четыре", "grade_student")
    assert params.get("student") == "Иванову"
    assert params.get("grade") == 4


def test_grade_sidorov_2_no_verb(extractor):
    params = extractor.extract("Сидоров 2", "grade_student")
    assert params.get("student") == "Сидоров"
    assert params.get("grade") == 2


def test_grade_petrovu_pyat(extractor):
    params = extractor.extract("выставь Петрову пять", "grade_student")
    assert params.get("student") == "Петрову"
    assert params.get("grade") == 5


def test_grade_with_ocenku_word(extractor):
    params = extractor.extract("поставь Иванову оценку четыре", "grade_student")
    assert params.get("student") == "Иванову"
    assert params.get("grade") == 4


def test_grade_math_2_plus_2_not_extracted(extractor):
    params = extractor.extract("сколько будет 2 плюс 2", "grade_student")
    assert params == {}, f"Математика не должна давать grade_student params: {params}"


def test_grade_math_word_only_not_extracted(extractor):
    params = extractor.extract("два плюс два", "grade_student")
    assert params == {}, f"Математика не должна давать grade_student params: {params}"


def test_grade_math_25_times_168_not_extracted(extractor):
    params = extractor.extract("25 умножить на 168", "grade_student")
    assert params == {}


def test_grade_math_with_explicit_verb_is_still_extracted(extractor):
    """
    "поставь Иванову четыре" — глагол есть, extraction проходит,
    даже если в тексте случайно есть "плюс" (но его тут нет).
    """
    params = extractor.extract("поставь Иванову четыре", "grade_student")
    assert params.get("student") == "Иванову"
    assert params.get("grade") == 4


def test_grade_missing_grade_not_extracted(extractor):
    params = extractor.extract("поставь Иванову", "grade_student")
    assert params == {}


def test_grade_empty_text(extractor):
    params = extractor.extract("", "grade_student")
    assert params == {}


# ---------------------------------------------------------------------------
# open_video / open_presentation: topic
# ---------------------------------------------------------------------------

def test_video_pro_elektrichestvo(extractor):
    params = extractor.extract("включи видео про электричество", "open_video")
    assert params.get("topic") == "электричество"


def test_video_rolik_pro_transformatory(extractor):
    params = extractor.extract("покажи ролик про трансформаторы", "open_video")
    assert params.get("topic") == "трансформаторы"


def test_video_po_ohrane_truda(extractor):
    params = extractor.extract("открой видео по охране труда", "open_video")
    assert params.get("topic") == "охране труда"


def test_presentation_po_fizike(extractor):
    params = extractor.extract("открой презентацию по физике", "open_presentation")
    assert params.get("topic") == "физике"


def test_presentation_pro_transformatory(extractor):
    params = extractor.extract("покажи презентацию про трансформаторы", "open_presentation")
    assert params.get("topic") == "трансформаторы"


def test_presentation_slidy_po_elektrobezopasnosti(extractor):
    params = extractor.extract("покажи слайды по электробезопасности", "open_presentation")
    assert params.get("topic") == "электробезопасности"


def test_video_without_topic_returns_empty(extractor):
    """
    "включи видео" — topic отсутствует. Не выдумывать "видео" как topic.
    """
    params = extractor.extract("включи видео", "open_video")
    assert params == {}, f"Не должно быть topic='видео': {params}"


def test_presentation_without_topic_returns_empty(extractor):
    params = extractor.extract("открой презентацию", "open_presentation")
    assert params == {}


def test_video_generic_word_na_temu_is_kept(extractor):
    """
    "на тему <тема>" — тоже валидный маркер.
    """
    params = extractor.extract("включи видео на тему трансформаторы", "open_video")
    assert params.get("topic") == "трансформаторы"


# ---------------------------------------------------------------------------
# next_slide / answer / unknown
# ---------------------------------------------------------------------------

def test_next_slide_empty_params(extractor):
    assert extractor.extract("следующий слайд", "next_slide") == {}


def test_next_slide_dalshe_empty_params(extractor):
    assert extractor.extract("дальше", "next_slide") == {}


def test_answer_empty_params(extractor):
    assert extractor.extract("привет", "answer") == {}


def test_answer_math_empty_params(extractor):
    assert extractor.extract("сколько будет 2 плюс 2", "answer") == {}


def test_unknown_empty_params(extractor):
    assert extractor.extract("абракадабра", "unknown") == {}


# ---------------------------------------------------------------------------
# Extractor НЕ меняет intent
# ---------------------------------------------------------------------------

def test_extractor_does_not_change_intent(extractor):
    """
    Проверка контракта: extractor принимает intent и возвращает только params.
    """
    params_1 = extractor.extract("поставь Иванову четыре", "grade_student")
    params_2 = extractor.extract("поставь Иванову четыре", "open_video")

    # Один и тот же текст, разные intent → разные params.
    assert params_1.get("student") == "Иванову"
    assert "student" not in params_2
    assert params_2 == {}  # в этом тексте нет "про/по/о", topic не извлекается


# ---------------------------------------------------------------------------
# Прямой запуск
# ---------------------------------------------------------------------------

def _run_all():
    tests = [
        test_grade_ivanovu_4,
        test_grade_sidorov_2_no_verb,
        test_grade_petrovu_pyat,
        test_grade_with_ocenku_word,
        test_grade_math_2_plus_2_not_extracted,
        test_grade_math_word_only_not_extracted,
        test_video_pro_elektrichestvo,
        test_presentation_po_fizike,
        test_video_without_topic_returns_empty,
    ]
    failed = 0
    for t in tests:
        try:
            t(ParameterExtractor())
            print(f"[OK] {t.__name__}", flush=True)
        except AssertionError as e:
            failed += 1
            print(f"[FAIL] {t.__name__}: {e}", flush=True)
        except Exception as e:
            failed += 1
            print(f"[ERROR] {t.__name__}: {type(e).__name__}: {e}", flush=True)
    print(flush=True)
    print(f"=== {len(tests) - failed}/{len(tests)} PARAMETER TESTS PASSED (direct) ===", flush=True)
    return failed


def main():
    if not os.path.exists("assistant"):
        print("Запускать из корня проекта.", flush=True)
        sys.exit(2)
    sys.exit(1 if _run_all() else 0)


if __name__ == "__main__":
    main()
