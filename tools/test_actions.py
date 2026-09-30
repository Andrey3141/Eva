"""
Тесты Actions изолированно.

  - GradeStudentAction — по фактическому контракту: планировщик, не пишет в файл;
  - OpenPresentationAction — реальный fuzzy-поиск в presentations_dir;
  - OpenVideoAction — реальный fuzzy-поиск в presentations_dir;
  - NextSlideAction — простой контракт.

OpenPresentationAction и OpenVideoAction требуют context.presentations_dir.
Тесты используют временную папку с файлами и мокают _open_file.

Запуск через pytest:
    pytest -v tools/test_actions.py

Никаких сетевых запросов, GUI, subprocess, внешних приложений.
Исходный data/test_gradebook.xlsx не изменяется.
"""
import os
import shutil
import sys
from unittest import mock

from assistant import paths
from assistant.actions.actions_impl import (
    GradeStudentAction,
    OpenPresentationAction,
    OpenVideoAction,
    NextSlideAction,
)
from assistant.actions.base import ActionContext, ActionResult
from assistant.gradebook import ExcelGradebook


# --- helpers ---

SUBJECT = "Электроснабжение"
LESSON = "17.09"
SOURCE_PATH = str(paths.gradebook_path())
TMP_DIR = str(paths.temp_dir() / "eva_actions_test")


def _fresh_copy(tag: str) -> str:
    if not os.path.exists(SOURCE_PATH):
        raise RuntimeError(
            f"Нет исходного журнала {SOURCE_PATH}. "
            "Сначала выполните: python -m tools.make_test_gradebook"
        )
    os.makedirs(TMP_DIR, exist_ok=True)
    dst = os.path.join(TMP_DIR, f"gradebook_actions_{tag}.xlsx")
    shutil.copyfile(SOURCE_PATH, dst)
    return dst


def _read_cell(path: str, cell: str, sheet: str = SUBJECT):
    gb = ExcelGradebook()
    gb.load(path)
    ws = gb.wb[sheet]
    return ws[cell].value


def _ctx(
    path: str,
    *,
    dry_run: bool = False,
    presentations_dir: str | None = None,
) -> ActionContext:
    gb = ExcelGradebook()
    gb.load(path)
    return ActionContext(
        addressed_to_assistant=True,
        current_subject=SUBJECT,
        current_lesson=LESSON,
        gradebook=gb,
        gradebook_path=path,
        known_students=gb.get_students(),
        dry_run=dry_run,
        presentations_dir=presentations_dir,
        presentation_match_threshold=0.70,
        presentation_ambiguity_margin=0.05,
    )


def _make_file(dir_path, name: str):
    from pathlib import Path
    f = Path(dir_path) / name
    f.write_bytes(b"fake")
    return f


# ---------------------------------------------------------------------------
# GradeStudentAction — планировщик, не пишет в файл
# ---------------------------------------------------------------------------

def test_grade_student_action_returns_plan_with_target():
    path = _fresh_copy("plan")
    ctx = _ctx(path, dry_run=False)

    assert _read_cell(path, "F2") is None

    action = GradeStudentAction()
    target = {"student": "Иванов Пётр Сергеевич",
              "sheet": SUBJECT, "row": 2, "column": "F", "cell": "F2"}

    result = action.run(
        params={"student": "Иванов Пётр Сергеевич", "grade": 5},
        context=ctx,
        target=target,
        current_grade=None,
    )

    assert isinstance(result, ActionResult)
    assert result.executed is False
    assert result.needs_confirmation is True
    assert result.dry_run is True
    assert result.details.get("target") == target
    assert result.details.get("current_grade") is None

    assert _read_cell(path, "F2") is None
    assert "Иванов" in result.message
    assert "F2" in result.message


def test_grade_student_action_does_not_call_save():
    path = _fresh_copy("nosave")
    ctx = _ctx(path, dry_run=False)

    original_save = ExcelGradebook.save
    save_calls = {"n": 0}

    def tracking_save(self):
        save_calls["n"] += 1
        raise RuntimeError("save() не должен вызываться из GradeStudentAction.run")

    ExcelGradebook.save = tracking_save
    try:
        action = GradeStudentAction()
        raised = False
        try:
            action.run(
                params={"student": "Иванов Пётр Сергеевич", "grade": 4},
                context=ctx,
                target={"student": "Иванов Пётр Сергеевич",
                        "sheet": SUBJECT, "row": 2, "column": "F", "cell": "F2"},
                current_grade=None,
            )
        except RuntimeError:
            raised = True

        assert raised is False
        assert save_calls["n"] == 0
    finally:
        ExcelGradebook.save = original_save


def test_grade_student_action_preserves_neighbours():
    path = _fresh_copy("neigh")
    ctx = _ctx(path, dry_run=False)

    before_e2 = _read_cell(path, "E2")
    before_f3 = _read_cell(path, "F3")

    action = GradeStudentAction()
    action.run(
        params={"student": "Иванов Пётр Сергеевич", "grade": 3},
        context=ctx,
        target={"student": "Иванов Пётр Сергеевич",
                "sheet": SUBJECT, "row": 2, "column": "F", "cell": "F2"},
        current_grade=None,
    )

    assert _read_cell(path, "E2") == before_e2
    assert _read_cell(path, "F3") == before_f3


def test_grade_student_action_reports_confirmation():
    path = _fresh_copy("confirm")
    ctx = _ctx(path, dry_run=True)

    action = GradeStudentAction()
    result = action.run(
        params={"student": "Иванов Пётр Сергеевич", "grade": 4},
        context=ctx,
        target={"student": "Иванов Пётр Сергеевич",
                "sheet": SUBJECT, "row": 2, "column": "F", "cell": "F2"},
        current_grade=None,
    )

    assert result.needs_confirmation is True
    assert _read_cell(path, "F2") is None


def test_grade_student_action_without_target():
    path = _fresh_copy("notarget")
    ctx = _ctx(path, dry_run=False)

    action = GradeStudentAction()
    result = action.run(
        params={"student": "Иванов Пётр Сергеевич", "grade": 3},
        context=ctx,
        target={},
        current_grade=None,
    )

    assert result.needs_confirmation is True
    assert "Ячейка пока не определена" in result.message
    assert _read_cell(path, "F2") is None


def test_grade_student_action_message_when_current_grade_set():
    path = _fresh_copy("curr")
    ctx = _ctx(path, dry_run=False)

    action = GradeStudentAction()
    result = action.run(
        params={"student": "Сидоров Алексей Дмитриевич", "grade": 3},
        context=ctx,
        target={"student": "Сидоров Алексей Дмитриевич",
                "sheet": SUBJECT, "row": 3, "column": "F", "cell": "F3"},
        current_grade=5,
    )

    assert "уже стоит" in result.message
    assert "Заменить" in result.message or "заменить" in result.message
    assert _read_cell(path, "F3") == 5


# ---------------------------------------------------------------------------
# OpenPresentationAction
# ---------------------------------------------------------------------------

def test_open_presentation_action_returns_result(tmp_path):
    _make_file(tmp_path, "Фотосинтез.pptx")
    path = _fresh_copy("op")
    ctx = _ctx(path, presentations_dir=str(tmp_path))

    action = OpenPresentationAction()
    with mock.patch("assistant.actions.actions_impl._open_file",
                    return_value=True) as m:
        result = action.run(params={"topic": "фотосинтез"}, context=ctx)

    assert result.executed is True
    assert m.call_count == 1
    assert "фотосинтез" in result.message.lower()
    assert result.details.get("topic") == "фотосинтез"
    assert result.details.get("reason") == "exact"


def test_open_presentation_action_empty_topic(tmp_path):
    path = _fresh_copy("op_empty")
    ctx = _ctx(path, presentations_dir=str(tmp_path))

    action = OpenPresentationAction()
    result = action.run(params={}, context=ctx)

    assert result.executed is False
    assert result.details.get("reason") == "no_topic"
    assert "уточните тему" in result.message.lower()


def test_open_presentation_action_without_presentations_dir():
    path = _fresh_copy("op_nodir")
    ctx = _ctx(path, presentations_dir=None)

    action = OpenPresentationAction()
    result = action.run(params={"topic": "физика"}, context=ctx)

    assert result.executed is False
    assert result.details.get("reason") == "no_dir"


# ---------------------------------------------------------------------------
# OpenVideoAction — новый контракт
# ---------------------------------------------------------------------------

def test_open_video_action_returns_result(tmp_path):
    """
    С presentations_dir + подходящим .mp4 + замоканным _open_file
    Action должен вернуть executed=True.
    """
    _make_file(tmp_path, "Трансформаторы.mp4")
    path = _fresh_copy("ov")
    ctx = _ctx(path, presentations_dir=str(tmp_path))

    action = OpenVideoAction()
    with mock.patch("assistant.actions.actions_impl._open_file",
                    return_value=True) as m:
        result = action.run(
            params={"topic": "трансформаторы"},
            context=ctx,
        )

    assert result.executed is True, f"message={result.message}"
    assert m.call_count == 1
    opened = m.call_args[0][0]
    assert "Трансформаторы" in opened.name
    assert result.details.get("topic") == "трансформаторы"
    assert result.details.get("reason") == "exact"


def test_open_video_action_empty_topic(tmp_path):
    """
    presentations_dir валиден, но topic пуст → executed=False,
    reason=no_topic.
    """
    path = _fresh_copy("ov_empty")
    ctx = _ctx(path, presentations_dir=str(tmp_path))

    action = OpenVideoAction()
    result = action.run(params={}, context=ctx)

    assert result.executed is False
    assert result.details.get("reason") == "no_topic"
    assert "уточните" in result.message.lower()


def test_open_video_action_without_presentations_dir():
    """
    presentations_dir=None → executed=False, reason=no_dir.
    """
    path = _fresh_copy("ov_nodir")
    ctx = _ctx(path, presentations_dir=None)

    action = OpenVideoAction()
    result = action.run(params={"topic": "трансформаторы"}, context=ctx)

    assert result.executed is False
    assert result.details.get("reason") == "no_dir"


def test_open_video_action_file_not_found(tmp_path):
    """
    Директория валидна, но нет подходящего файла → executed=False.
    """
    path = _fresh_copy("ov_nofile")
    ctx = _ctx(path, presentations_dir=str(tmp_path))

    action = OpenVideoAction()
    result = action.run(params={"topic": "несуществующая тема"}, context=ctx)

    assert result.executed is False
    assert result.details.get("reason") in ("not_found", "below_threshold")


# ---------------------------------------------------------------------------
# NextSlideAction
# ---------------------------------------------------------------------------

def test_next_slide_action_returns_result():
    path = _fresh_copy("ns")
    ctx = _ctx(path)
    action = NextSlideAction()
    result = action.run(params={}, context=ctx)
    assert isinstance(result, ActionResult)
    assert result.executed is True
    assert "следующий" in result.message.lower() or "слайд" in result.message.lower()


# ---------------------------------------------------------------------------
# Прямой запуск
# ---------------------------------------------------------------------------

def _cleanup():
    if os.path.isdir(TMP_DIR):
        shutil.rmtree(TMP_DIR, ignore_errors=True)


def main():
    if not os.path.exists("assistant"):
        print("Запускать из корня проекта.", flush=True)
        sys.exit(2)
    print("Запуск через pytest: pytest -v tools/test_actions.py", flush=True)
    sys.exit(0)


if __name__ == "__main__":
    main()
