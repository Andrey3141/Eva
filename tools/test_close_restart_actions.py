"""
Тесты close_* и restart_* actions.

Системный запрос на закрытие окон мокается
(assistant.actions.actions_impl.close_window_for_file).

Контракт:
  - close_window_for_file возвращает CloseResult(status, message, matched_title).
  - status="close_requested" — команда ОТПРАВЛЕНА в найденное окно.
    Это не гарантирует фактическое закрытие.
  - last_opened_* очищается только при "close_requested".
  - при not_found/ambiguous/unsupported/error состояние сохраняется.
  - restart при "unsupported"/"ambiguous"/"error" НЕ открывает заново.
  - restart при "close_requested"/"not_found" открывает заново.
"""
import sys
from pathlib import Path
from unittest import mock

import pytest

from assistant.actions.actions_impl import (
    CloseFileAction, ClosePresentationAction,
    CloseVideoAction, CloseExcelAction,
    RestartPresentationAction, RestartExcelAction,
    OpenExcelAction,
    OpenPresentationAction,
)
from assistant.actions.base import ActionContext
from assistant.actions.window_control import CloseResult


def _ctx(**kwargs) -> ActionContext:
    defaults = dict(addressed_to_assistant=True)
    defaults.update(kwargs)
    return ActionContext(**defaults)


def _make_file(dir_path, name: str) -> Path:
    f = Path(dir_path) / name
    f.write_bytes(b"fake")
    return f


# ===========================================================================
# close — без открытого файла
# ===========================================================================

def test_close_presentation_without_open():
    ctx = _ctx()
    r = ClosePresentationAction().run({}, ctx)
    assert r.executed is False
    assert r.details.get("reason") == "no_last_opened"
    assert "не открыта" in r.message.lower()


def test_close_video_without_open():
    ctx = _ctx()
    r = CloseVideoAction().run({}, ctx)
    assert r.executed is False
    assert r.details.get("reason") == "no_last_opened"


def test_close_excel_without_open():
    ctx = _ctx()
    r = CloseExcelAction().run({}, ctx)
    assert r.executed is False
    assert r.details.get("reason") == "no_last_opened"


def test_close_file_without_open():
    ctx = _ctx()
    r = CloseFileAction().run({}, ctx)
    assert r.executed is False
    assert "нечего закрывать" in r.message.lower()


# ===========================================================================
# close — с открытым файлом
# ===========================================================================

def test_close_presentation_success(tmp_path):
    f = _make_file(tmp_path, "Физика.pptx")
    ctx = _ctx(
        last_opened_type="presentation",
        last_opened_path=str(f),
        last_opened_app="powerpoint",
    )
    with mock.patch(
        "assistant.actions.actions_impl.close_window_for_file",
        return_value=CloseResult("close_requested",
                                 matched_title="Физика"),
    ) as m:
        r = ClosePresentationAction().run({}, ctx)
    assert r.executed is True
    assert r.details.get("status") == "close_requested"
    assert m.call_count == 1
    assert ctx.last_opened_path is None
    assert ctx.last_opened_type is None


def test_close_presentation_not_found_keeps_state(tmp_path):
    f = _make_file(tmp_path, "Физика.pptx")
    ctx = _ctx(
        last_opened_type="presentation",
        last_opened_path=str(f),
        last_opened_app="powerpoint",
    )
    with mock.patch(
        "assistant.actions.actions_impl.close_window_for_file",
        return_value=CloseResult("not_found", "окно не найдено"),
    ):
        r = ClosePresentationAction().run({}, ctx)
    assert r.executed is False
    assert r.details.get("status") == "not_found"
    assert ctx.last_opened_path == str(f)


def test_close_presentation_ambiguous_keeps_state(tmp_path):
    f = _make_file(tmp_path, "Физика.pptx")
    ctx = _ctx(
        last_opened_type="presentation",
        last_opened_path=str(f),
        last_opened_app="powerpoint",
    )
    with mock.patch(
        "assistant.actions.actions_impl.close_window_for_file",
        return_value=CloseResult("ambiguous", "несколько окон"),
    ):
        r = ClosePresentationAction().run({}, ctx)
    assert r.executed is False
    assert r.details.get("status") == "ambiguous"
    assert ctx.last_opened_path == str(f)


def test_close_presentation_unsupported_keeps_state(tmp_path):
    f = _make_file(tmp_path, "Физика.pptx")
    ctx = _ctx(
        last_opened_type="presentation",
        last_opened_path=str(f),
        last_opened_app="powerpoint",
    )
    with mock.patch(
        "assistant.actions.actions_impl.close_window_for_file",
        return_value=CloseResult("unsupported", "wmctrl недоступен"),
    ):
        r = ClosePresentationAction().run({}, ctx)
    assert r.executed is False
    assert r.details.get("status") == "unsupported"
    assert "не поддерживается" in r.message.lower()
    assert ctx.last_opened_path == str(f)


def test_close_presentation_error_keeps_state(tmp_path):
    f = _make_file(tmp_path, "Физика.pptx")
    ctx = _ctx(
        last_opened_type="presentation",
        last_opened_path=str(f),
        last_opened_app="powerpoint",
    )
    with mock.patch(
        "assistant.actions.actions_impl.close_window_for_file",
        return_value=CloseResult("error", "PostMessageW failed"),
    ):
        r = ClosePresentationAction().run({}, ctx)
    assert r.executed is False
    assert r.details.get("status") == "error"
    assert ctx.last_opened_path == str(f)


def test_close_presentation_wrong_kind(tmp_path):
    f = _make_file(tmp_path, "Физика.mp4")
    ctx = _ctx(
        last_opened_type="video",
        last_opened_path=str(f),
        last_opened_app="vlc",
    )
    r = ClosePresentationAction().run({}, ctx)
    assert r.executed is False
    assert r.details.get("reason") == "no_last_opened"


def test_close_video_success(tmp_path):
    f = _make_file(tmp_path, "Ролик.mp4")
    ctx = _ctx(
        last_opened_type="video",
        last_opened_path=str(f),
        last_opened_app="vlc",
    )
    with mock.patch(
        "assistant.actions.actions_impl.close_window_for_file",
        return_value=CloseResult("close_requested"),
    ):
        r = CloseVideoAction().run({}, ctx)
    assert r.executed is True
    assert ctx.last_opened_path is None


def test_close_excel_success(tmp_path):
    f = _make_file(tmp_path, "Журнал.xlsx")
    ctx = _ctx(
        last_opened_type="excel",
        last_opened_path=str(f),
        last_opened_app="excel",
    )
    with mock.patch(
        "assistant.actions.actions_impl.close_window_for_file",
        return_value=CloseResult("close_requested"),
    ):
        r = CloseExcelAction().run({}, ctx)
    assert r.executed is True


def test_close_file_closes_any_kind(tmp_path):
    f = _make_file(tmp_path, "Документ.docx")
    ctx = _ctx(
        last_opened_type="presentation",
        last_opened_path=str(f),
        last_opened_app="powerpoint",
    )
    with mock.patch(
        "assistant.actions.actions_impl.close_window_for_file",
        return_value=CloseResult("close_requested"),
    ):
        r = CloseFileAction().run({}, ctx)
    assert r.executed is True


# ===========================================================================
# restart
# ===========================================================================

def test_restart_presentation_without_last():
    ctx = _ctx()
    r = RestartPresentationAction().run({}, ctx)
    assert r.executed is False
    assert r.details.get("reason") == "no_last_opened"


def test_restart_presentation_success(tmp_path):
    f = _make_file(tmp_path, "Физика.pptx")
    ctx = _ctx(
        last_opened_type="presentation",
        last_opened_path=str(f),
        last_opened_app="powerpoint",
    )
    with mock.patch(
        "assistant.actions.actions_impl.close_window_for_file",
        return_value=CloseResult("close_requested"),
    ), mock.patch(
        "assistant.actions.actions_impl._open_file",
        return_value=True,
    ) as m_open:
        r = RestartPresentationAction().run({}, ctx)
    assert r.executed is True
    assert m_open.call_count == 1
    assert ctx.last_opened_path == str(f)
    assert ctx.last_opened_type == "presentation"


def test_restart_presentation_not_found_still_opens(tmp_path):
    f = _make_file(tmp_path, "Физика.pptx")
    ctx = _ctx(
        last_opened_type="presentation",
        last_opened_path=str(f),
        last_opened_app="powerpoint",
    )
    with mock.patch(
        "assistant.actions.actions_impl.close_window_for_file",
        return_value=CloseResult("not_found"),
    ), mock.patch(
        "assistant.actions.actions_impl._open_file",
        return_value=True,
    ) as m_open:
        r = RestartPresentationAction().run({}, ctx)
    assert r.executed is True
    assert m_open.call_count == 1


def test_restart_presentation_ambiguous_does_not_open(tmp_path):
    f = _make_file(tmp_path, "Физика.pptx")
    ctx = _ctx(
        last_opened_type="presentation",
        last_opened_path=str(f),
        last_opened_app="powerpoint",
    )
    with mock.patch(
        "assistant.actions.actions_impl.close_window_for_file",
        return_value=CloseResult("ambiguous"),
    ), mock.patch(
        "assistant.actions.actions_impl._open_file",
        return_value=True,
    ) as m_open:
        r = RestartPresentationAction().run({}, ctx)
    assert r.executed is False
    assert r.details.get("reason") == "ambiguous"
    assert m_open.call_count == 0


def test_restart_presentation_unsupported_does_not_open(tmp_path):
    f = _make_file(tmp_path, "Физика.pptx")
    ctx = _ctx(
        last_opened_type="presentation",
        last_opened_path=str(f),
        last_opened_app="powerpoint",
    )
    with mock.patch(
        "assistant.actions.actions_impl.close_window_for_file",
        return_value=CloseResult("unsupported", "нет wmctrl"),
    ), mock.patch(
        "assistant.actions.actions_impl._open_file",
        return_value=True,
    ) as m_open:
        r = RestartPresentationAction().run({}, ctx)
    assert r.executed is False
    assert r.details.get("reason") == "unsupported"
    assert m_open.call_count == 0


def test_restart_presentation_error_does_not_open(tmp_path):
    f = _make_file(tmp_path, "Физика.pptx")
    ctx = _ctx(
        last_opened_type="presentation",
        last_opened_path=str(f),
        last_opened_app="powerpoint",
    )
    with mock.patch(
        "assistant.actions.actions_impl.close_window_for_file",
        return_value=CloseResult("error", "boom"),
    ), mock.patch(
        "assistant.actions.actions_impl._open_file",
        return_value=True,
    ) as m_open:
        r = RestartPresentationAction().run({}, ctx)
    assert r.executed is False
    assert r.details.get("reason") == "close_error"
    assert m_open.call_count == 0


def test_restart_presentation_path_missing(tmp_path):
    ctx = _ctx(
        last_opened_type="presentation",
        last_opened_path=str(tmp_path / "gone.pptx"),
        last_opened_app="powerpoint",
    )
    r = RestartPresentationAction().run({}, ctx)
    assert r.executed is False
    assert r.details.get("reason") == "path_missing"


def test_restart_excel_success(tmp_path):
    f = _make_file(tmp_path, "Журнал.xlsx")
    ctx = _ctx(
        last_opened_type="excel",
        last_opened_path=str(f),
        last_opened_app="excel",
    )
    with mock.patch(
        "assistant.actions.actions_impl.close_window_for_file",
        return_value=CloseResult("close_requested"),
    ), mock.patch(
        "assistant.actions.actions_impl._open_file",
        return_value=True,
    ):
        r = RestartExcelAction().run({}, ctx)
    assert r.executed is True


# ===========================================================================
# open_excel
# ===========================================================================

def test_open_excel_no_dir():
    ctx = _ctx(presentations_dir=None)
    r = OpenExcelAction().run({"topic": "журнал"}, ctx)
    assert r.executed is False
    assert r.details.get("reason") == "no_dir"


def test_open_excel_no_topic(tmp_path):
    ctx = _ctx(presentations_dir=str(tmp_path))
    r = OpenExcelAction().run({}, ctx)
    assert r.executed is False
    assert r.details.get("reason") == "no_topic"


def test_open_excel_xlsx(tmp_path):
    _make_file(tmp_path, "Журнал 2024.xlsx")
    ctx = _ctx(presentations_dir=str(tmp_path))
    with mock.patch(
        "assistant.actions.actions_impl._open_file",
        return_value=True,
    ) as m:
        r = OpenExcelAction().run({"topic": "журнал 2024"}, ctx)
    assert r.executed is True
    assert m.call_count == 1
    assert ctx.last_opened_type == "excel"


def test_open_excel_xls(tmp_path):
    _make_file(tmp_path, "Отчёт.xls")
    ctx = _ctx(presentations_dir=str(tmp_path))
    with mock.patch(
        "assistant.actions.actions_impl._open_file",
        return_value=True,
    ):
        r = OpenExcelAction().run({"topic": "отчёт"}, ctx)
    assert r.executed is True


def test_open_excel_xlsm(tmp_path):
    _make_file(tmp_path, "Макрос.xlsm")
    ctx = _ctx(presentations_dir=str(tmp_path))
    with mock.patch(
        "assistant.actions.actions_impl._open_file",
        return_value=True,
    ):
        r = OpenExcelAction().run({"topic": "макрос"}, ctx)
    assert r.executed is True


def test_open_excel_no_match(tmp_path):
    _make_file(tmp_path, "Химия.xlsx")
    ctx = _ctx(presentations_dir=str(tmp_path))
    r = OpenExcelAction().run({"topic": "физика"}, ctx)
    assert r.executed is False


# ===========================================================================
# Состояние last_opened_* — полный цикл
# ===========================================================================

def test_state_open_close_cycle(tmp_path):
    f = _make_file(tmp_path, "Физика.pptx")
    ctx = _ctx(presentations_dir=str(tmp_path))

    with mock.patch(
        "assistant.actions.actions_impl._open_file",
        return_value=True,
    ):
        r_open = OpenPresentationAction().run({"topic": "физика"}, ctx)
    assert r_open.executed is True
    assert ctx.last_opened_type == "presentation"
    assert ctx.last_opened_path == str(f)

    with mock.patch(
        "assistant.actions.actions_impl.close_window_for_file",
        return_value=CloseResult("close_requested"),
    ):
        r_close = ClosePresentationAction().run({}, ctx)
    assert r_close.executed is True
    assert ctx.last_opened_type is None
    assert ctx.last_opened_path is None


def test_state_open_close_not_found_keeps_state(tmp_path):
    f = _make_file(tmp_path, "Физика.pptx")
    ctx = _ctx(presentations_dir=str(tmp_path))

    with mock.patch(
        "assistant.actions.actions_impl._open_file",
        return_value=True,
    ):
        OpenPresentationAction().run({"topic": "физика"}, ctx)
    assert ctx.last_opened_path == str(f)

    with mock.patch(
        "assistant.actions.actions_impl.close_window_for_file",
        return_value=CloseResult("not_found"),
    ):
        r = ClosePresentationAction().run({}, ctx)
    assert r.executed is False
    assert ctx.last_opened_path == str(f)


def test_state_restart_keeps_state(tmp_path):
    f = _make_file(tmp_path, "Физика.pptx")
    ctx = _ctx(
        last_opened_type="presentation",
        last_opened_path=str(f),
        last_opened_app="powerpoint",
    )
    with mock.patch(
        "assistant.actions.actions_impl.close_window_for_file",
        return_value=CloseResult("close_requested"),
    ), mock.patch(
        "assistant.actions.actions_impl._open_file",
        return_value=True,
    ):
        r = RestartPresentationAction().run({}, ctx)
    assert r.executed is True
    assert ctx.last_opened_path == str(f)
    assert ctx.last_opened_type == "presentation"


def run_all():
    print("pytest -v tools/test_close_restart_actions.py", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(run_all())
