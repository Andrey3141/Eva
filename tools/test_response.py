"""
Тесты слоя Response.

  - EchoResponseGenerator — офлайн-шаблоны;
  - LLMResponseGenerator — с FakeLLM, без сети.

Запуск через pytest:
    pytest -v tools/test_response.py
Прямой запуск:
    python -m tools.test_response

Никаких сетевых запросов, реальных LLM, TTS, GUI.
"""
import os
import sys

from assistant.intent.base import Intent
from assistant.response.base import ResponseGenerator
from assistant.response.echo_response import EchoResponseGenerator
from assistant.response.llm_response import LLMResponseGenerator


# ---------------------------------------------------------------------------
# FakeLLM
# ---------------------------------------------------------------------------

class FakeLLM:
    """
    Возвращает заранее заданные ответы по порядку.
    Запоминает последний (user_message, system_prompt) для проверки.
    """
    def __init__(self, scripted: list[str]):
        self._script = list(scripted)
        self.calls = 0
        self.last_user_message: str | None = None
        self.last_system_prompt: str | None = None

    def chat(self, user_message: str, system_prompt: str | None = None) -> str:
        self.calls += 1
        self.last_user_message = user_message
        self.last_system_prompt = system_prompt
        if not self._script:
            return ""
        return self._script.pop(0)

    def name(self) -> str:
        return "fake"


def _answer_intent(text: str = "привет") -> Intent:
    return Intent(name="answer", params={}, confidence=0.9, raw_text=text)


def _grade_intent(student: str = "Сидорову", grade: int = 2) -> Intent:
    return Intent(
        name="grade_student",
        params={"student": student, "grade": grade},
        confidence=0.96,
    )


# ---------------------------------------------------------------------------
# Контракт базового класса
# ---------------------------------------------------------------------------

def test_response_generator_is_abstract():
    """
    ResponseGenerator — абстрактный: нельзя создать экземпляр без
    реализации generate. Это контракт base.py.
    """
    try:
        ResponseGenerator()  # type: ignore[abstract]
        assert False, "ResponseGenerator() не должен создаваться напрямую"
    except TypeError:
        pass


def test_echo_and_llm_are_response_generators():
    e = EchoResponseGenerator()
    l = LLMResponseGenerator(FakeLLM(["x"]))
    assert isinstance(e, ResponseGenerator)
    assert isinstance(l, ResponseGenerator)


# ---------------------------------------------------------------------------
# EchoResponseGenerator
# ---------------------------------------------------------------------------

def test_echo_answer_returns_said_phrase():
    g = EchoResponseGenerator()
    out = g.generate("привет", _answer_intent("привет"))
    assert isinstance(out, str)
    assert out == "Вы сказали: привет"


def test_echo_answer_uses_raw_text_over_command():
    """
    Если intent.raw_text задан, эхо отдаёт его, а не user_command.
    Это фактическое поведение echo_response.
    """
    g = EchoResponseGenerator()
    it = Intent(name="answer", params={}, confidence=0.6, raw_text="очищенный текст")
    out = g.generate("сырой текст", it)
    assert out == "Вы сказали: очищенный текст"


def test_echo_answer_empty_raw_text_falls_back_to_command():
    g = EchoResponseGenerator()
    it = Intent(name="answer", params={}, confidence=0.6, raw_text="")
    out = g.generate("привет", it)
    assert out == "Вы сказали: привет"


def test_echo_answer_empty_both_returns_listening():
    g = EchoResponseGenerator()
    it = Intent(name="answer", params={}, confidence=0.6, raw_text="")
    out = g.generate("", it)
    # echo_response: если текста нет совсем — «Я вас слушаю.»
    assert out == "Я вас слушаю."


def test_echo_grade_student_uses_params():
    g = EchoResponseGenerator()
    out = g.generate("поставь Сидорову два", _grade_intent("Сидорову", 2))
    assert "Сидорову" in out
    assert "2" in out


def test_echo_grade_student_without_params_uses_defaults():
    g = EchoResponseGenerator()
    it = Intent(name="grade_student", params={}, confidence=0.9)
    out = g.generate("x", it)
    # echo_response: student по умолчанию "ученику", grade "?"
    assert "ученику" in out
    assert "?" in out


def test_echo_next_slide_fixed_phrase():
    g = EchoResponseGenerator()
    it = Intent(name="next_slide", params={}, confidence=0.97)
    out = g.generate("следующий слайд", it)
    assert "слайд" in out.lower()


def test_echo_unknown_action_uses_action_result():
    g = EchoResponseGenerator()
    it = Intent(name="open_presentation", params={"topic": "физика"}, confidence=0.9)
    out = g.generate("открой презентацию", it, action_result="Открываю физику.")
    assert out == "Открываю физику."


def test_echo_unknown_action_without_action_result_returns_fallback():
    g = EchoResponseGenerator()
    it = Intent(name="open_presentation", params={"topic": "физика"}, confidence=0.9)
    out = g.generate("открой презентацию", it, action_result=None)
    # echo_response: fallback-строка
    assert "open_presentation" in out or "не поддерживается" in out


# ---------------------------------------------------------------------------
# LLMResponseGenerator
# ---------------------------------------------------------------------------

def test_llm_answer_success_returns_llm_text():
    llm = FakeLLM(["Здравствуйте! Чем могу помочь?"])
    g = LLMResponseGenerator(llm)
    out = g.generate("привет", _answer_intent("привет"))
    assert out == "Здравствуйте! Чем могу помочь?"
    assert llm.calls == 1


def test_llm_answer_prompt_includes_user_command():
    llm = FakeLLM(["ок"])
    g = LLMResponseGenerator(llm)
    g.generate("привет", _answer_intent("привет"))
    assert llm.last_user_message is not None
    assert "привет" in llm.last_user_message
    # system_prompt должен быть задан (SYSTEM_PROMPT модуля)
    assert llm.last_system_prompt
    assert isinstance(llm.last_system_prompt, str)
    assert len(llm.last_system_prompt) > 0


def test_llm_answer_empty_response_is_returned_as_is():
    """
    Текущий контракт: LLMResponseGenerator не подменяет пустой ответ LLM
    на что-то другое — возвращает как есть.
    """
    llm = FakeLLM([""])
    g = LLMResponseGenerator(llm)
    out = g.generate("привет", _answer_intent("привет"))
    assert out == ""


def test_llm_action_with_action_result_returns_action_result():
    """
    Если intent — действие и action_result задан, LLM не вызывается,
    возвращается action_result.
    """
    llm = FakeLLM(["не должен быть вызван"])
    g = LLMResponseGenerator(llm)
    it = _grade_intent("Сидорову", 2)
    out = g.generate("поставь Сидорову два", it, action_result="Готово.")
    assert out == "Готово."
    assert llm.calls == 0


def test_llm_action_without_action_result_returns_stub():
    llm = FakeLLM(["не должен быть вызван"])
    g = LLMResponseGenerator(llm)
    it = _grade_intent("Сидорову", 2)
    out = g.generate("поставь Сидорову два", it, action_result=None)
    assert out == "Выполняю: grade_student."
    assert llm.calls == 0


def test_llm_action_next_slide_without_action_result_returns_stub():
    llm = FakeLLM(["не должен быть вызван"])
    g = LLMResponseGenerator(llm)
    it = Intent(name="next_slide", params={}, confidence=0.9)
    out = g.generate("следующий слайд", it, action_result=None)
    assert "next_slide" in out
    assert llm.calls == 0


def test_llm_error_from_llm_propagates():
    """
    Текущий контракт: LLMResponseGenerator не ловит исключения LLM.
    Если LLM.chat бросает — исключение пробрасывается наружу.
    """
    class BrokenLLM:
        def chat(self, user_message, system_prompt=None):
            raise RuntimeError("llm down")

        def name(self):
            return "broken"

    g = LLMResponseGenerator(BrokenLLM())
    raised = False
    try:
        g.generate("привет", _answer_intent("привет"))
    except RuntimeError:
        raised = True
    assert raised is True


# ---------------------------------------------------------------------------
# Прямой запуск
# ---------------------------------------------------------------------------

def _run_all():
    tests = [
        test_response_generator_is_abstract,
        test_echo_and_llm_are_response_generators,
        test_echo_answer_returns_said_phrase,
        test_echo_answer_uses_raw_text_over_command,
        test_echo_answer_empty_raw_text_falls_back_to_command,
        test_echo_answer_empty_both_returns_listening,
        test_echo_grade_student_uses_params,
        test_echo_grade_student_without_params_uses_defaults,
        test_echo_next_slide_fixed_phrase,
        test_echo_unknown_action_uses_action_result,
        test_echo_unknown_action_without_action_result_returns_fallback,
        test_llm_answer_success_returns_llm_text,
        test_llm_answer_prompt_includes_user_command,
        test_llm_answer_empty_response_is_returned_as_is,
        test_llm_action_with_action_result_returns_action_result,
        test_llm_action_without_action_result_returns_stub,
        test_llm_action_next_slide_without_action_result_returns_stub,
        test_llm_error_from_llm_propagates,
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
    print(f"=== {len(tests) - failed}/{len(tests)} RESPONSE TESTS PASSED ===", flush=True)
    return failed


def main():
    if not os.path.exists("assistant"):
        print("Запускать из корня проекта.", flush=True)
        sys.exit(2)
    sys.exit(1 if _run_all() else 0)


if __name__ == "__main__":
    main()
