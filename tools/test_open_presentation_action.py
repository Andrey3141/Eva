"""
Тесты OpenPresentationAction — токен-ориентированный fuzzy-поиск.

Системное открытие замокано (assistant.actions.actions_impl._open_file).

Контракт:
  - ровно один exact → reason="exact".
  - несколько exact → reason="ambiguous", ambiguous_kind="exact".
  - fuzzy top-1 ≥ threshold, не неоднозначно → reason="fuzzy_auto_open".
  - fuzzy top-1 и top-2 оба ≥ threshold, разница < margin →
    reason="ambiguous", ambiguous_kind="fuzzy".
  - fuzzy top-1 < threshold → reason="below_threshold".

Пороги берутся из ActionContext.
"""
import sys
from pathlib import Path
from unittest import mock

import pytest

from assistant.actions.actions_impl import (
    OpenPresentationAction,
    _similarity,
    _normalize,
)
from assistant.actions.base import ActionContext


def _ctx(dir_path, threshold=0.70, margin=0.05):
    return ActionContext(
        addressed_to_assistant=True,
        presentations_dir=str(dir_path),
        presentation_match_threshold=threshold,
        presentation_ambiguity_margin=margin,
    )


def _make_file(dir_path: Path, name: str) -> Path:
    f = dir_path / name
    f.write_bytes(b"fake")
    return f


def _name_of(path_str: str) -> str:
    return path_str.replace("\\", "/").rsplit("/", 1)[-1]


# ---------------------------------------------------------------------------
# 0. Утилиты
# ---------------------------------------------------------------------------

def test_normalize_handles_case_and_yo():
    assert _normalize("Трансформаторы") == "трансформаторы"
    assert _normalize("Ёлка") == "елка"
    assert _normalize("  Много   пробелов  ") == "много пробелов"


def test_similarity_exact():
    assert _similarity("физика", "физика") == 1.0


def test_similarity_typo_high():
    s = _similarity("трансформатары", "трансформаторы")
    assert s >= 0.70, f"score={s:.3f}"


def test_similarity_extra_words_dont_break():
    s = _similarity("трансформаторы", "трансформаторы 9 класс")
    assert s >= 0.70, f"score={s:.3f}"


def test_similarity_short_word_in_long_name_not_high():
    s = _similarity(
        "физика",
        "физика электрических цепей и основы электроснабжения",
    )
    assert s < 0.70, f"score={s:.3f}"


def test_similarity_unrelated_low():
    s = _similarity("электроснабжение", "трансформаторы")
    assert s < 0.70


def test_similarity_numeric_tokens_strict():
    assert _similarity("лекция 1", "лекция 1") == 1.0
    s2 = _similarity("лекция 1", "лекция 10")
    assert s2 < 0.70, f"score={s2:.3f}"
    s3 = _similarity("лекция 9", "лекция 10")
    assert s3 < 0.70, f"score={s3:.3f}"


def test_similarity_empty():
    assert _similarity("", "физика") == 0.0
    assert _similarity("физика", "") == 0.0


# ---------------------------------------------------------------------------
# 1. Ошибки конфигурации
# ---------------------------------------------------------------------------

def test_no_presentations_dir_returns_error():
    action = OpenPresentationAction()
    ctx = ActionContext(addressed_to_assistant=True, presentations_dir=None)
    result = action.run({"topic": "физика"}, ctx)
    assert result.executed is False
    assert result.details.get("reason") == "no_dir"


def test_missing_dir_returns_error(tmp_path):
    action = OpenPresentationAction()
    ctx = _ctx(tmp_path / "no_such_dir")
    result = action.run({"topic": "физика"}, ctx)
    assert result.executed is False
    assert result.details.get("reason") == "dir_missing"


def test_empty_topic_does_not_open(tmp_path):
    _make_file(tmp_path, "Физика.pptx")
    action = OpenPresentationAction()
    ctx = _ctx(tmp_path)
    result = action.run({}, ctx)
    assert result.executed is False
    assert result.details.get("reason") == "no_topic"


# ---------------------------------------------------------------------------
# 2. Exact — ровно один, приоритет над fuzzy
# ---------------------------------------------------------------------------

def test_single_exact_still_opens(tmp_path):
    _make_file(tmp_path, "Физика.pptx")
    action = OpenPresentationAction()
    ctx = _ctx(tmp_path)

    with mock.patch("assistant.actions.actions_impl._open_file",
                    return_value=True) as m:
        result = action.run({"topic": "физика"}, ctx)

    assert result.executed is True
    assert m.call_count == 1
    assert _name_of(m.call_args[0][0].name) == "Физика.pptx"
    assert result.details.get("reason") == "exact"
    assert result.details.get("score") == pytest.approx(1.0)


def test_exact_wins_over_fuzzy(tmp_path):
    _make_file(tmp_path, "Физика.pptx")
    _make_file(tmp_path, "Физика 9 класс.pptx")
    action = OpenPresentationAction()
    ctx = _ctx(tmp_path)

    with mock.patch("assistant.actions.actions_impl._open_file",
                    return_value=True) as m:
        result = action.run({"topic": "физика"}, ctx)

    assert result.executed is True
    assert _name_of(m.call_args[0][0].name) == "Физика.pptx"
    assert result.details.get("reason") == "exact"


def test_exact_case_insensitive(tmp_path):
    _make_file(tmp_path, "ФИЗИКА.pptx")
    action = OpenPresentationAction()
    ctx = _ctx(tmp_path)

    with mock.patch("assistant.actions.actions_impl._open_file",
                    return_value=True):
        result = action.run({"topic": "физика"}, ctx)

    assert result.executed is True
    assert result.details.get("reason") == "exact"


# ---------------------------------------------------------------------------
# 3. Несколько exact — ambiguous
# ---------------------------------------------------------------------------

def test_multiple_exact_candidates_ambiguous(tmp_path):
    """
    Физика.pptx + Физика.pdf.
    Оба is_exact=True → не открывать автоматически, вернуть ambiguous
    со списком обоих файлов.
    """
    _make_file(tmp_path, "Физика.pptx")
    _make_file(tmp_path, "Физика.pdf")
    action = OpenPresentationAction()
    ctx = _ctx(tmp_path)

    with mock.patch("assistant.actions.actions_impl._open_file",
                    return_value=True) as m:
        result = action.run({"topic": "физика"}, ctx)

    assert result.executed is False
    assert m.call_count == 0, "Не должно быть попытки открытия"
    assert result.details.get("reason") == "ambiguous"
    assert result.details.get("ambiguous_kind") == "exact"

    candidates = result.details.get("candidates") or []
    assert len(candidates) == 2
    names = {_name_of(c["path"]) for c in candidates}
    assert names == {"Физика.pptx", "Физика.pdf"}

    assert "несколько" in result.message.lower()
    assert "какой" in result.message.lower()


def test_multiple_exact_case_insensitive(tmp_path):
    """
    ФИЗИКА.pptx + физика.pdf — оба нормализуются в "физика",
    оба is_exact=True → ambiguous.
    """
    _make_file(tmp_path, "ФИЗИКА.pptx")
    _make_file(tmp_path, "физика.pdf")
    action = OpenPresentationAction()
    ctx = _ctx(tmp_path)

    with mock.patch("assistant.actions.actions_impl._open_file",
                    return_value=True) as m:
        result = action.run({"topic": "физика"}, ctx)

    assert result.executed is False
    assert m.call_count == 0
    assert result.details.get("reason") == "ambiguous"
    assert result.details.get("ambiguous_kind") == "exact"


def test_three_exact_candidates_ambiguous(tmp_path):
    _make_file(tmp_path, "Физика.pptx")
    _make_file(tmp_path, "Физика.pdf")
    _make_file(tmp_path, "Физика.odp")
    action = OpenPresentationAction()
    ctx = _ctx(tmp_path)

    with mock.patch("assistant.actions.actions_impl._open_file",
                    return_value=True) as m:
        result = action.run({"topic": "физика"}, ctx)

    assert result.executed is False
    assert m.call_count == 0
    assert result.details.get("ambiguous_kind") == "exact"
    candidates = result.details.get("candidates") or []
    assert len(candidates) == 3


# ---------------------------------------------------------------------------
# 4. Fuzzy auto open
# ---------------------------------------------------------------------------

def test_transsformers_with_number_is_not_exact(tmp_path):
    _make_file(tmp_path, "Трансформаторы 9 класс.pptx")
    action = OpenPresentationAction()
    ctx = _ctx(tmp_path)

    with mock.patch("assistant.actions.actions_impl._open_file",
                    return_value=True):
        result = action.run({"topic": "трансформаторы"}, ctx)

    assert result.executed is True
    assert result.details.get("reason") == "fuzzy_auto_open"


def test_fuzzy_typo(tmp_path):
    _make_file(tmp_path, "Трансформаторы.pptx")
    action = OpenPresentationAction()
    ctx = _ctx(tmp_path)

    with mock.patch("assistant.actions.actions_impl._open_file",
                    return_value=True):
        result = action.run({"topic": "трансформатары"}, ctx)

    assert result.executed is True
    assert result.details.get("reason") == "fuzzy_auto_open"


# ---------------------------------------------------------------------------
# 5. Below threshold
# ---------------------------------------------------------------------------

def test_below_threshold_unrelated(tmp_path):
    _make_file(tmp_path, "Электроснабжение.pptx")
    action = OpenPresentationAction()
    ctx = _ctx(tmp_path)

    with mock.patch("assistant.actions.actions_impl._open_file",
                    return_value=True) as m:
        result = action.run({"topic": "трансформаторы"}, ctx)

    assert result.executed is False
    assert m.call_count == 0
    assert result.details.get("reason") == "below_threshold"


def test_short_topic_in_long_unrelated_name(tmp_path):
    _make_file(
        tmp_path,
        "Физика электрических цепей и основы электроснабжения.pptx",
    )
    action = OpenPresentationAction()
    ctx = _ctx(tmp_path)

    with mock.patch("assistant.actions.actions_impl._open_file",
                    return_value=True) as m:
        result = action.run({"topic": "физика"}, ctx)

    assert result.executed is False, (
        f"Короткое 'физика' в длинном нерелевантном названии не должно "
        f"открывать файл. score={result.details.get('top_score')}"
    )
    assert m.call_count == 0


def test_empty_directory_not_found(tmp_path):
    action = OpenPresentationAction()
    ctx = _ctx(tmp_path)
    result = action.run({"topic": "физика"}, ctx)
    assert result.executed is False
    assert result.details.get("reason") == "not_found"


# ---------------------------------------------------------------------------
# 6. Fuzzy неоднозначность
# ---------------------------------------------------------------------------

def test_two_numbered_ambiguous(tmp_path):
    _make_file(tmp_path, "Трансформаторы 9.pptx")
    _make_file(tmp_path, "Трансформаторы 10.pptx")
    action = OpenPresentationAction()
    ctx = _ctx(tmp_path)

    with mock.patch("assistant.actions.actions_impl._open_file",
                    return_value=True) as m:
        result = action.run({"topic": "трансформаторы"}, ctx)

    assert result.executed is False
    assert m.call_count == 0
    assert result.details.get("reason") == "ambiguous"
    assert result.details.get("ambiguous_kind") == "fuzzy"


def test_lecture_1_vs_9_10_ambiguous(tmp_path):
    _make_file(tmp_path, "Лекция 9.pptx")
    _make_file(tmp_path, "Лекция 10.pptx")
    action = OpenPresentationAction()
    ctx = _ctx(tmp_path)

    with mock.patch("assistant.actions.actions_impl._open_file",
                    return_value=True) as m:
        result = action.run({"topic": "лекция 1"}, ctx)

    assert result.executed is False, (
        f"Не должно быть автоматического открытия. "
        f"reason={result.details.get('reason')}"
    )
    assert m.call_count == 0
    assert result.details.get("reason") in ("below_threshold", "ambiguous")


# ---------------------------------------------------------------------------
# 7. Настройки threshold и margin из context
# ---------------------------------------------------------------------------

def test_custom_threshold_blocks_open(tmp_path):
    _make_file(tmp_path, "Трансформаторы 9 класс.pptx")
    action = OpenPresentationAction()
    ctx = _ctx(tmp_path, threshold=0.99, margin=0.05)

    with mock.patch("assistant.actions.actions_impl._open_file",
                    return_value=True) as m:
        result = action.run({"topic": "трансформаторы"}, ctx)

    assert result.executed is False
    assert m.call_count == 0
    assert result.details.get("reason") == "below_threshold"


def test_custom_threshold_allows_open(tmp_path):
    _make_file(tmp_path, "Трансформаторы 9 класс.pptx")
    action = OpenPresentationAction()
    ctx = _ctx(tmp_path, threshold=0.30, margin=0.05)

    with mock.patch("assistant.actions.actions_impl._open_file",
                    return_value=True):
        result = action.run({"topic": "трансформаторы"}, ctx)

    assert result.executed is True


def test_custom_margin_affects_ambiguity(tmp_path):
    _make_file(tmp_path, "Физика 9 класс.pptx")
    _make_file(tmp_path, "Физика 10 класс.pptx")

    action = OpenPresentationAction()
    ctx_ambig = _ctx(tmp_path, threshold=0.30, margin=0.99)

    with mock.patch("assistant.actions.actions_impl._open_file",
                    return_value=True):
        result = action.run({"topic": "физика"}, ctx_ambig)

    assert result.details.get("reason") == "ambiguous"


# ---------------------------------------------------------------------------
# 8. Форматы и открытие
# ---------------------------------------------------------------------------

def test_unsupported_ext_not_considered(tmp_path):
    (tmp_path / "Физика.txt").write_text("x", encoding="utf-8")
    action = OpenPresentationAction()
    ctx = _ctx(tmp_path)
    result = action.run({"topic": "физика"}, ctx)
    assert result.executed is False


def test_pdf_supported(tmp_path):
    _make_file(tmp_path, "Физика.pdf")
    action = OpenPresentationAction()
    ctx = _ctx(tmp_path)

    with mock.patch("assistant.actions.actions_impl._open_file",
                    return_value=True):
        result = action.run({"topic": "физика"}, ctx)

    assert result.executed is True


def test_odp_supported(tmp_path):
    _make_file(tmp_path, "Физика.odp")
    action = OpenPresentationAction()
    ctx = _ctx(tmp_path)

    with mock.patch("assistant.actions.actions_impl._open_file",
                    return_value=True):
        result = action.run({"topic": "физика"}, ctx)

    assert result.executed is True


def test_open_failure_returns_error(tmp_path):
    _make_file(tmp_path, "Физика.pptx")
    action = OpenPresentationAction()
    ctx = _ctx(tmp_path)

    with mock.patch("assistant.actions.actions_impl._open_file",
                    return_value=False):
        result = action.run({"topic": "физика"}, ctx)

    assert result.executed is False
    assert result.details.get("reason") == "open_failed"


def run_all():
    print("Запуск через pytest: pytest -v tools/test_open_presentation_action.py",
          flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(run_all())
