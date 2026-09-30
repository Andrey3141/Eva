"""
Тесты IntentParser.

  - EchoIntentParser (офлайн-эвристики) — unit-тесты.
  - LLMIntentParser (JSON от LLM) — unit-тесты с FakeLLM.

Сценарии, которые EchoIntentParser архитектурно не покрывает
(открытие презентации/видео, распознавание математических фраз),
перенесены в tools/test_intent_router_scenarios.py и проверяются
на каскадном IntentRouter.

Запуск через pytest:
    pytest -v tools/test_intent.py
"""
import os
import sys

from assistant.intent.base import Intent, IntentParser
from assistant.intent.echo_intent_parser import EchoIntentParser
from assistant.intent.llm_intent_parser import LLMIntentParser


class FakeLLM:
    def __init__(self, scripted: list[str]):
        self._script = list(scripted)
        self.calls = 0

    def chat(self, user_message: str, system_prompt: str | None = None) -> str:
        self.calls += 1
        if not self._script:
            return ""
        return self._script.pop(0)

    def name(self) -> str:
        return "fake"


# ---------------------------------------------------------------------------
# EchoIntentParser — unit
# ---------------------------------------------------------------------------

def _echo_parse(text: str) -> list[Intent]:
    parser = EchoIntentParser()
    return parser.parse(text)


def test_echo_grade_student_ivanovu_4():
    intents = _echo_parse("поставь Иванову четыре")
    assert len(intents) == 1
    it = intents[0]
    assert it.name == "grade_student", it.name
    assert it.params.get("student") == "Иванову", it.params
    assert it.params.get("grade") == 4, it.params


def test_echo_grade_student_sidorovu_3():
    intents = _echo_parse("поставь Сидорову три")
    assert len(intents) == 1
    it = intents[0]
    assert it.name == "grade_student", it.name
    assert it.params.get("student") == "Сидорову", it.params
    assert it.params.get("grade") == 3, it.params


def test_echo_grade_student_no_verb():
    intents = _echo_parse("Сидоров 2")
    assert len(intents) == 1
    it = intents[0]
    assert it.name == "grade_student", it.name
    assert it.params.get("student") == "Сидоров", it.params
    assert it.params.get("grade") == 2, it.params


def test_echo_next_slide():
    intents = _echo_parse("следующий слайд")
    assert len(intents) == 1
    assert intents[0].name == "next_slide"


def test_echo_next_slide_dalshe():
    intents = _echo_parse("дальше слайд")
    assert len(intents) == 1
    assert intents[0].name == "next_slide"


def test_echo_unknown_is_answer():
    intents = _echo_parse("Сидоров завтра будет")
    assert len(intents) == 1
    assert intents[0].name == "answer"


def test_echo_empty_is_answer():
    intents = _echo_parse("")
    assert len(intents) == 1
    assert intents[0].name == "answer"


# ---------------------------------------------------------------------------
# LLMIntentParser — unit с FakeLLM
# ---------------------------------------------------------------------------

def _llm_parse(llm_response: str) -> list[Intent]:
    llm = FakeLLM([llm_response])
    parser = LLMIntentParser(llm)
    return parser.parse("тестовый запрос")


def test_llm_valid_grade_student_json():
    response = (
        '{"intent": "grade_student", '
        '"params": {"student": "Сидорову", "grade": 2}, '
        '"confidence": 0.96}'
    )
    intents = _llm_parse(response)
    assert len(intents) == 1
    it = intents[0]
    assert it.name == "grade_student"
    assert it.params.get("student") == "Сидорову"
    assert it.params.get("grade") == 2
    assert abs(it.confidence - 0.96) < 1e-6


def test_llm_answer_json():
    response = '{"intent": "answer", "params": {}, "confidence": 0.9}'
    intents = _llm_parse(response)
    assert len(intents) == 1
    assert intents[0].name == "answer"


def test_llm_multiple_intents_in_array():
    response = (
        '['
        '{"intent": "open_file", "params": {"target": "таблицу"}, "confidence": 0.9},'
        '{"intent": "grade_student", "params": {"student": "Сидорову", "grade": 2}, "confidence": 0.95}'
        ']'
    )
    intents = _llm_parse(response)
    assert len(intents) == 2, len(intents)
    names = [i.name for i in intents]
    assert "open_file" in names
    assert "grade_student" in names


def test_llm_invalid_json_falls_back_to_answer():
    response = "Извините, я не могу разобрать этот запрос как JSON."
    intents = _llm_parse(response)
    assert len(intents) == 1
    assert intents[0].name == "answer", intents[0].name


def test_llm_json_wrapped_in_text():
    response = (
        "Вот результат:\n"
        '{"intent": "grade_student", "params": {"student": "Иванову", "grade": 5}, "confidence": 0.9}\n'
        "Готово."
    )
    intents = _llm_parse(response)
    assert len(intents) == 1
    assert intents[0].name == "grade_student"
    assert intents[0].params.get("grade") == 5


def test_llm_empty_response_is_answer():
    intents = _llm_parse("")
    assert len(intents) == 1
    assert intents[0].name == "answer"


def test_llm_unknown_intent_is_preserved():
    response = '{"intent": "unknown_thing", "params": {}, "confidence": 0.5}'
    intents = _llm_parse(response)
    assert len(intents) == 1
    assert intents[0].name == "unknown_thing"


# ---------------------------------------------------------------------------
# Структурная валидация Intent
# ---------------------------------------------------------------------------

def test_intent_is_action_classification():
    assert Intent(name="grade_student").is_action() is True
    assert Intent(name="open_file").is_action() is True
    assert Intent(name="next_slide").is_action() is True
    assert Intent(name="answer").is_action() is False
    assert Intent(name="unknown").is_action() is False
    assert Intent(name="").is_action() is False


def test_grade_student_required_params_present():
    intents = _echo_parse("поставь Иванову четыре")
    it = intents[0]
    assert it.name == "grade_student"
    assert "student" in it.params and it.params["student"]
    assert "grade" in it.params and it.params["grade"] in (2, 3, 4, 5)


def test_grade_student_missing_param_not_silently_accepted():
    response = '{"intent": "grade_student", "params": {"grade": 3}, "confidence": 0.9}'
    intents = _llm_parse(response)
    assert len(intents) == 1
    it = intents[0]
    assert it.name == "grade_student"
    assert "student" not in it.params or not it.params.get("student")


# ---------------------------------------------------------------------------
# Прямой запуск
# ---------------------------------------------------------------------------

def _run_all():
    tests = [
        test_echo_grade_student_ivanovu_4,
        test_echo_grade_student_sidorovu_3,
        test_echo_grade_student_no_verb,
        test_echo_next_slide,
        test_echo_next_slide_dalshe,
        test_echo_unknown_is_answer,
        test_echo_empty_is_answer,
        test_llm_valid_grade_student_json,
        test_llm_answer_json,
        test_llm_multiple_intents_in_array,
        test_llm_invalid_json_falls_back_to_answer,
        test_llm_json_wrapped_in_text,
        test_llm_empty_response_is_answer,
        test_llm_unknown_intent_is_preserved,
        test_intent_is_action_classification,
        test_grade_student_required_params_present,
        test_grade_student_missing_param_not_silently_accepted,
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
    if failed == 0:
        print(f"=== ALL {len(tests)} INTENT TESTS PASSED ===", flush=True)
    else:
        print(f"=== {failed} of {len(tests)} INTENT TESTS FAILED ===", flush=True)
    return failed


def main():
    if not os.path.exists("assistant"):
        print("Запускать из корня проекта.", flush=True)
        sys.exit(2)
    sys.exit(1 if _run_all() else 0)


if __name__ == "__main__":
    main()
