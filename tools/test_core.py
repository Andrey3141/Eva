"""
Тесты AssistantCore — фактический контракт.

  - обычная команда проходит pipeline;
  - confirmation создаёт pending и ждёт;
  - «да» выполняет pending, «нет» отменяет;
  - pending очищается после выполнения/отмены;
  - подтверждение без pending безопасно;
  - stale-state перепроверяется перед записью;
  - ошибка save() не выдаётся как success;
  - TTS и IntentParser замоканы.

Запуск через pytest:
    pytest -v tools/test_core.py
Прямой запуск:
    python -m tools.test_core

Никакой сети, Whisper, Silero, GUI, реального Excel.
"""
import os
import shutil
import sys

import numpy as np

from assistant import paths
from assistant.core import AssistantCore
from assistant.wake.keyword_detector import KeywordWakeDetector
from assistant.intent.echo_intent_parser import EchoIntentParser
from assistant.response.echo_response import EchoResponseGenerator
from assistant.actions.base import ActionRegistry, ActionContext
from assistant.actions.actions_impl import (
    GradeStudentAction,
    OpenPresentationAction,
    OpenVideoAction,
    NextSlideAction,
)
from assistant.actions.validators import (
    GradeStudentValidator,
    OpenPresentationValidator,
    OpenVideoValidator,
    NextSlideValidator,
)
from assistant.gradebook import ExcelGradebook
from assistant.confirmation import KeywordConfirmationParser


SUBJECT = "Электроснабжение"
LESSON = "17.09"
SOURCE_PATH = str(paths.gradebook_path())
TMP_DIR = str(paths.temp_dir() / "eva_core_test")


# ---------------------------------------------------------------------------
# Заглушки
# ---------------------------------------------------------------------------

class ScriptedSTT:
    def __init__(self):
        self.next_text = ""

    def transcribe(self, audio, sample_rate) -> str:
        return self.next_text


class SilentTTS:
    def __init__(self):
        self.spoken: list[str] = []

    def speak(self, text: str) -> None:
        if text:
            self.spoken.append(text)


# ---------------------------------------------------------------------------
# Инфраструктура
# ---------------------------------------------------------------------------

def _fresh_copy(tag: str) -> str:
    if not os.path.exists(SOURCE_PATH):
        raise RuntimeError(
            f"Нет исходного журнала {SOURCE_PATH}. "
            "Сначала выполните: python -m tools.make_test_gradebook"
        )
    os.makedirs(TMP_DIR, exist_ok=True)
    dst = os.path.join(TMP_DIR, f"gradebook_core_{tag}.xlsx")
    shutil.copyfile(SOURCE_PATH, dst)
    return dst


def _cleanup():
    if os.path.isdir(TMP_DIR):
        shutil.rmtree(TMP_DIR, ignore_errors=True)


def _make_core(stt, tts, path):
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
        tts=tts,
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
# 1. Обычная команда проходит через Core
# ---------------------------------------------------------------------------

def test_core_answer_pipeline():
    path = _fresh_copy("answer")
    stt = ScriptedSTT()
    tts = SilentTTS()
    core = _make_core(stt, tts, path)

    r = _run(core, stt, "Ассистент, привет")

    assert r.is_addressed is True
    assert r.recognized_text == "Ассистент, привет"
    assert r.final_speech
    assert "привет" in r.final_speech.lower() or "сказали" in r.final_speech.lower()
    assert tts.spoken, "TTS должен быть вызван"
    assert core.pending_confirmation is None


def test_core_command_ignores_non_addressed():
    path = _fresh_copy("ignore")
    stt = ScriptedSTT()
    tts = SilentTTS()
    core = _make_core(stt, tts, path)

    r = _run(core, stt, "Сидоров завтра будет")
    assert r.is_addressed is False
    assert core.pending_confirmation is None
    assert tts.spoken == []


# ---------------------------------------------------------------------------
# 2. Confirmation создаёт pending, action НЕ выполняется
# ---------------------------------------------------------------------------

def test_core_grade_command_creates_pending_without_write():
    path = _fresh_copy("pend")
    stt = ScriptedSTT()
    tts = SilentTTS()
    core = _make_core(stt, tts, path)

    assert _read_cell(path, "F2") is None

    _run(core, stt, "Ассистент, поставь Иванову четыре")

    assert core.pending_confirmation is not None
    assert core.pending_confirmation.action_name == "grade_student"
    assert core.pending_confirmation.previous_grade is None

    # Файл не тронут
    assert _read_cell(path, "F2") is None


def test_core_pending_cleared_after_yes():
    path = _fresh_copy("yes")
    stt = ScriptedSTT()
    tts = SilentTTS()
    core = _make_core(stt, tts, path)

    _run(core, stt, "Ассистент, поставь Иванову четыре")
    assert core.pending_confirmation is not None

    r = _run(core, stt, "да")
    assert core.pending_confirmation is None
    assert _read_cell(path, "F2") == 4
    assert "Готово" in r.final_speech or "оценка" in r.final_speech.lower()


def test_core_pending_cleared_after_no():
    path = _fresh_copy("no")
    stt = ScriptedSTT()
    tts = SilentTTS()
    core = _make_core(stt, tts, path)

    _run(core, stt, "Ассистент, поставь Иванову четыре")
    assert core.pending_confirmation is not None

    _run(core, stt, "нет")
    assert core.pending_confirmation is None
    assert _read_cell(path, "F2") is None


# ---------------------------------------------------------------------------
# 3. Confirmation без pending безопасен
# ---------------------------------------------------------------------------

def test_core_yes_without_pending_is_safe():
    path = _fresh_copy("nopend_yes")
    stt = ScriptedSTT()
    tts = SilentTTS()
    core = _make_core(stt, tts, path)

    assert core.pending_confirmation is None
    r = _run(core, stt, "Ассистент, да")
    # Ничего не выполнено, pending пуст
    assert core.pending_confirmation is None
    assert _read_cell(path, "F2") is None


def test_core_no_without_pending_is_safe():
    path = _fresh_copy("nopend_no")
    stt = ScriptedSTT()
    tts = SilentTTS()
    core = _make_core(stt, tts, path)

    assert core.pending_confirmation is None
    _run(core, stt, "Ассистент, нет")
    assert core.pending_confirmation is None
    assert _read_cell(path, "F2") is None


# ---------------------------------------------------------------------------
# 4. Stale-state перепроверяется
# ---------------------------------------------------------------------------

def test_core_stale_state_recheck():
    path = _fresh_copy("stale")
    stt = ScriptedSTT()
    tts = SilentTTS()
    core = _make_core(stt, tts, path)

    _run(core, stt, "Ассистент, поставь Иванову четыре")
    assert core.pending_confirmation is not None
    assert core.pending_confirmation.previous_grade is None

    # Внешнее изменение
    _external_set_cell(path, "F2", 5)
    assert _read_cell(path, "F2") == 5

    # Первое «да» — Core должен обнаружить изменение и запросить снова
    _run(core, stt, "да")
    assert _read_cell(path, "F2") == 5, "Core не должен перезаписывать stale-значение"
    assert core.pending_confirmation is not None
    assert core.pending_confirmation.previous_grade == 5

    # Второе «да» — теперь записываем
    _run(core, stt, "да")
    assert _read_cell(path, "F2") == 4
    assert core.pending_confirmation is None


# ---------------------------------------------------------------------------
# 5. Ошибка save() не выдаётся как success
# ---------------------------------------------------------------------------

def test_core_save_error_is_not_success():
    path = _fresh_copy("savefail")
    stt = ScriptedSTT()
    tts = SilentTTS()
    core = _make_core(stt, tts, path)

    original_save = ExcelGradebook.save

    def broken_save(self):
        raise RuntimeError("disk full")

    ExcelGradebook.save = broken_save
    try:
        _run(core, stt, "Ассистент, поставь Иванову четыре")
        r = _run(core, stt, "да")

        assert core.pending_confirmation is None
        assert "Не удалось сохранить" in r.final_speech or "не удалось" in r.final_speech.lower()
        assert "Готово" not in r.final_speech
    finally:
        ExcelGradebook.save = original_save


# ---------------------------------------------------------------------------
# 6. После отмены следующее сообщение не выполняет старое действие
# ---------------------------------------------------------------------------

def test_core_after_cancel_next_message_is_independent():
    path = _fresh_copy("after_cancel")
    stt = ScriptedSTT()
    tts = SilentTTS()
    core = _make_core(stt, tts, path)

    _run(core, stt, "Ассистент, поставь Иванову четыре")
    assert core.pending_confirmation is not None

    _run(core, stt, "нет")
    assert core.pending_confirmation is None
    assert _read_cell(path, "F2") is None

    # Следующее обычное сообщение не выполняет старое действие
    r = _run(core, stt, "Ассистент, привет")
    assert core.pending_confirmation is None
    assert _read_cell(path, "F2") is None


# ---------------------------------------------------------------------------
# 7. Повторное подтверждение после выполненного действия
# ---------------------------------------------------------------------------

def test_core_yes_after_success_is_noop():
    path = _fresh_copy("yes_after")
    stt = ScriptedSTT()
    tts = SilentTTS()
    core = _make_core(stt, tts, path)

    _run(core, stt, "Ассистент, поставь Иванову четыре")
    _run(core, stt, "да")
    assert _read_cell(path, "F2") == 4
    assert core.pending_confirmation is None

    # Повторное «да» без pending
    _run(core, stt, "Ассистент, да")
    assert _read_cell(path, "F2") == 4
    assert core.pending_confirmation is None


# ---------------------------------------------------------------------------
# 8. Core не зависит от cwd
# ---------------------------------------------------------------------------

def test_core_cwd_independent(tmp_path, monkeypatch):
    path = _fresh_copy("cwd")
    stt = ScriptedSTT()
    tts = SilentTTS()
    core = _make_core(stt, tts, path)

    other = tmp_path / "elsewhere"
    other.mkdir()
    monkeypatch.chdir(other)

    _run(core, stt, "Ассистент, поставь Иванову четыре")
    _run(core, stt, "да")
    assert _read_cell(path, "F2") == 4


# ---------------------------------------------------------------------------
# Прямой запуск
# ---------------------------------------------------------------------------

def _run_all():
    # Прямой запуск — три простых теста без tmp_path/monkeypatch.
    tests = [
        test_core_answer_pipeline,
        test_core_command_ignores_non_addressed,
        test_core_grade_command_creates_pending_without_write,
        test_core_pending_cleared_after_yes,
        test_core_pending_cleared_after_no,
        test_core_yes_without_pending_is_safe,
        test_core_no_without_pending_is_safe,
        test_core_stale_state_recheck,
        test_core_save_error_is_not_success,
        test_core_after_cancel_next_message_is_independent,
        test_core_yes_after_success_is_noop,
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
    print(f"=== {len(tests) - failed}/{len(tests)} CORE TESTS PASSED (direct) ===", flush=True)
    return failed


def main():
    if not os.path.exists("assistant"):
        print("Запускать из корня проекта.", flush=True)
        sys.exit(2)
    try:
        failed = _run_all()
    finally:
        _cleanup()
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
