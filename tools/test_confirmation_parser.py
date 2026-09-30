"""
Тесты KeywordConfirmationParser.

Запуск через pytest:
    pytest -v tools/test_confirmation_parser.py
Прямой запуск:
    python -m tools.test_confirmation_parser
"""
import sys

from assistant.confirmation import KeywordConfirmationParser
from assistant.confirmation.base import ConfirmationDecision


def _parse(text: str):
    return KeywordConfirmationParser().parse(text)


def test_yes_da():
    assert _parse("да") == ConfirmationDecision.YES


def test_yes_aga():
    assert _parse("ага") == ConfirmationDecision.YES


def test_yes_konechno():
    assert _parse("конечно") == ConfirmationDecision.YES


def test_yes_podtverzhdayu():
    assert _parse("подтверждаю") == ConfirmationDecision.YES


def test_yes_vypolnyay():
    assert _parse("выполняй") == ConfirmationDecision.YES


def test_no_net():
    assert _parse("нет") == ConfirmationDecision.NO


def test_no_ne_nado():
    assert _parse("не надо") == ConfirmationDecision.NO


def test_no_otmena():
    assert _parse("отмена") == ConfirmationDecision.NO


def test_no_ne_stav():
    assert _parse("не ставь") == ConfirmationDecision.NO


def test_unknown_empty():
    assert _parse("") == ConfirmationDecision.UNKNOWN


def test_unknown_random_phrase():
    assert _parse("Сидоров завтра будет") == ConfirmationDecision.UNKNOWN


def test_case_insensitive():
    assert _parse("ДА") == ConfirmationDecision.YES
    assert _parse("Нет") == ConfirmationDecision.NO


def test_yes_inside_sentence():
    # "да, конечно" — должно распознаваться как YES
    assert _parse("да, конечно") == ConfirmationDecision.YES


def test_no_inside_sentence():
    assert _parse("нет, не надо") == ConfirmationDecision.NO


def test_no_wins_over_yes_when_both_present():
    """
    Если в тексте есть и «нет», и «да» — текущая реализация сначала
    проверяет NO-паттерны, потом YES. Это её явное поведение.
    """
    assert _parse("нет, хотя да") == ConfirmationDecision.NO


def run_all():
    tests = [
        test_yes_da,
        test_yes_aga,
        test_yes_konechno,
        test_yes_podtverzhdayu,
        test_yes_vypolnyay,
        test_no_net,
        test_no_ne_nado,
        test_no_otmena,
        test_no_ne_stav,
        test_unknown_empty,
        test_unknown_random_phrase,
        test_case_insensitive,
        test_yes_inside_sentence,
        test_no_inside_sentence,
        test_no_wins_over_yes_when_both_present,
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
    print(f"=== {len(tests) - failed}/{len(tests)} CONFIRMATION PARSER TESTS PASSED ===", flush=True)
    return failed


def main():
    import os
    if not os.path.exists("assistant"):
        print("Запускать из корня проекта.", flush=True)
        sys.exit(2)
    sys.exit(1 if run_all() else 0)


if __name__ == "__main__":
    main()
