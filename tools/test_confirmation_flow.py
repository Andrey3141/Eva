"""
Сценарии подтверждения grade_student без микрофона.
Каждый сценарий работает с ИЗОЛИРОВАННОЙ копией исходного журнала.
Исходный журнал не изменяется.

Запуск через pytest:
    pytest -v tools/test_confirmation_flow.py
Прямой запуск:
    python -m tools.test_confirmation_flow
"""
import os
import shutil

import numpy as np

from assistant import paths
from assistant.core import AssistantCore
from assistant.wake.keyword_detector import KeywordWakeDetector
from assistant.intent.echo_intent_parser import EchoIntentParser
from assistant.response.echo_response import EchoResponseGenerator
from assistant.actions.base import ActionRegistry, ActionContext
from assistant.actions.actions_impl import (
    GradeStudentAction, OpenPresentationAction,
    OpenVideoAction, NextSlideAction,
)
from assistant.actions.validators import (
    GradeStudentValidator, OpenPresentationValidator,
    OpenVideoValidator, NextSlideValidator,
)
from assistant.gradebook import ExcelGradebook
from assistant.confirmation import KeywordConfirmationParser


class ScriptedSTT:
    def __init__(self):
        self.next_text = ""

    def transcribe(self, audio, sample_rate) -> str:
        return self.next_text


class SilentTTS:
    def speak(self, text: str) -> None:
        print(f"[TTS] {text}", flush=True)


SUBJECT = "Электроснабжение"
LESSON = "17.09"
SOURCE_PATH = str(paths.gradebook_path())
TMP_DIR = str(paths.temp_dir() / "eva_confirmation_test")


def _fresh_copy(tag: str) -> str:
    if not os.path.exists(SOURCE_PATH):
        raise RuntimeError(
            f"Нет исходного журнала {SOURCE_PATH}. "
            "Сначала выполните: python -m tools.make_test_gradebook"
        )
    os.makedirs(TMP_DIR, exist_ok=True)
    dst = os.path.join(TMP_DIR, f"gradebook_{tag}.xlsx")
    shutil.copyfile(SOURCE_PATH, dst)
    return dst


def _cleanup():
    if os.path.isdir(TMP_DIR):
        shutil.rmtree(TMP_DIR, ignore_errors=True)


def _make_core(stt, path):
    gb = ExcelGradebook()
    gb.load(path)

    reg = ActionRegistry()
    reg.register(GradeStudentAction(), GradeStudentValidator())
    reg.register(OpenPresentationAction(), OpenPresentationValidator())
    reg.register(OpenVideoAction(), OpenVideoValidator())
    reg.register(NextSlideAction(), NextSlideValidator())

    ctx = ActionContext(
        addressed_to_assistant=False,
        current_subject=SUBJECT,
        current_lesson=LESSON,
        gradebook=gb,
        gradebook_path=path,
        known_students=gb.get_students(),
        dry_run=False,
    )

    return AssistantCore(
        stt=stt,
        wake=KeywordWakeDetector(),
        intent_parser=EchoIntentParser(),
        response_gen=EchoResponseGenerator(),
        actions=reg,
        tts=SilentTTS(),
        confirmation_parser=KeywordConfirmationParser(),
        context=ctx,
    )


def _run(core, stt, text):
    stt.next_text = text
    return core.handle_audio(np.zeros(16000, dtype="float32"), 16000)


def _read_cell(path: str, cell: str, sheet: str = SUBJECT):
    gb = ExcelGradebook()
    gb.load(path)
    ws = gb.wb[sheet]
    return ws[cell].value


def _external_set_cell(path: str, cell: str, value, sheet: str = SUBJECT) -> None:
    gb = ExcelGradebook()
    gb.load(path)
    ws = gb.wb[sheet]
    ws[cell] = value
    gb.save()


# ---------------------------------------------------------------------------
# Сценарии
# ---------------------------------------------------------------------------

def test_scenario_a_empty_cell_confirm_write():
    """A. Пустая ячейка → 'да' → запись."""
    path = _fresh_copy("a")
    stt = ScriptedSTT()
    core = _make_core(stt, path)

    r1 = _run(core, stt, "Ассистент, поставь Иванову четыре")
    assert core.pending_confirmation is not None

    r2 = _run(core, stt, "да")
    assert _read_cell(path, "F2") == 4
    assert core.pending_confirmation is None


def test_scenario_b_existing_grade_cancel():
    """B. Существующая оценка → 'нет' → без изменений."""
    path = _fresh_copy("b")
    stt = ScriptedSTT()
    core = _make_core(stt, path)

    r1 = _run(core, stt, "Ассистент, поставь Сидорову три")
    assert core.pending_confirmation is not None

    r2 = _run(core, stt, "нет")
    assert _read_cell(path, "F3") == 5
    assert core.pending_confirmation is None


def test_scenario_c_existing_grade_confirm_replace():
    """C. Существующая оценка → 'да' → замена."""
    path = _fresh_copy("c")
    stt = ScriptedSTT()
    core = _make_core(stt, path)

    r1 = _run(core, stt, "Ассистент, поставь Сидорову три")
    assert core.pending_confirmation is not None
    assert core.pending_confirmation.previous_grade == 5

    r2 = _run(core, stt, "да")
    assert _read_cell(path, "F3") == 3
    assert core.pending_confirmation is None


def test_scenario_d_change_between_confirmations():
    """D. Изменение ячейки между запросом и подтверждением."""
    path = _fresh_copy("d")
    stt = ScriptedSTT()
    core = _make_core(stt, path)

    assert _read_cell(path, "F2") is None

    r1 = _run(core, stt, "Ассистент, поставь Иванову четыре")
    assert core.pending_confirmation is not None
    assert core.pending_confirmation.previous_grade is None

    # Внешнее изменение
    _external_set_cell(path, "F2", 5)
    assert _read_cell(path, "F2") == 5

    # Первое «да» — система должна обнаружить изменение и запросить снова
    r2 = _run(core, stt, "да")
    assert _read_cell(path, "F2") == 5
    assert core.pending_confirmation is not None
    assert core.pending_confirmation.previous_grade == 5

    # Второе «да» — теперь запись
    r3 = _run(core, stt, "да")
    assert _read_cell(path, "F2") == 4
    assert core.pending_confirmation is None


def test_scenario_e_cancel_empty_cell():
    """E. Отмена на пустой ячейке."""
    path = _fresh_copy("e")
    stt = ScriptedSTT()
    core = _make_core(stt, path)

    assert _read_cell(path, "F2") is None

    r1 = _run(core, stt, "Ассистент, поставь Иванову четыре")
    assert core.pending_confirmation is not None

    r2 = _run(core, stt, "нет")
    assert _read_cell(path, "F2") is None
    assert core.pending_confirmation is None


def test_scenario_f_save_error():
    """F. Ошибка save() → сообщение об ошибке, файл не изменён."""
    path = _fresh_copy("f")
    stt = ScriptedSTT()
    core = _make_core(stt, path)

    original_save = ExcelGradebook.save

    def broken_save(self):
        raise RuntimeError("disk full")

    ExcelGradebook.save = broken_save
    try:
        r1 = _run(core, stt, "Ассистент, поставь Иванову четыре")
        assert core.pending_confirmation is not None

        r2 = _run(core, stt, "да")
        assert "Не удалось сохранить" in r2.final_speech, r2.final_speech
        assert core.pending_confirmation is None
        assert _read_cell(path, "F2") is None
    finally:
        ExcelGradebook.save = original_save


# ---------------------------------------------------------------------------
# Прямой запуск
# ---------------------------------------------------------------------------

def main():
    if not os.path.exists(SOURCE_PATH):
        print("Сначала создайте журнал: python -m tools.make_test_gradebook", flush=True)
        return

    try:
        print("\n=== A. Пустая ячейка ===", flush=True)
        test_scenario_a_empty_cell_confirm_write()
        print("[OK]", flush=True)

        print("\n=== B. Существующая оценка, отмена ===", flush=True)
        test_scenario_b_existing_grade_cancel()
        print("[OK]", flush=True)

        print("\n=== C. Существующая оценка, подтверждение ===", flush=True)
        test_scenario_c_existing_grade_confirm_replace()
        print("[OK]", flush=True)

        print("\n=== D. Изменение между подтверждением ===", flush=True)
        test_scenario_d_change_between_confirmations()
        print("[OK]", flush=True)

        print("\n=== E. Отмена (пустая ячейка) ===", flush=True)
        test_scenario_e_cancel_empty_cell()
        print("[OK]", flush=True)

        print("\n=== F. Ошибка сохранения ===", flush=True)
        test_scenario_f_save_error()
        print("[OK]", flush=True)
    finally:
        _cleanup()

    print("\n=== ALL SCENARIOS PASSED ===", flush=True)


if __name__ == "__main__":
    main()
