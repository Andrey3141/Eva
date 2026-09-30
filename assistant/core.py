from dataclasses import dataclass, field
from typing import Callable, Optional
import threading
import traceback

from .stt.base import STTEngine
from .wake.base import WakeDetector
from .intent.base import Intent, IntentParser
from .response.base import ResponseGenerator
from .actions.base import (
    ActionRegistry,
    ActionResult,
    ValidationResult,
    ActionContext,
)
from .gradebook.base import Gradebook
from .confirmation.base import ConfirmationDecision, ConfirmationParser
from .tts.base import TTSEngine


@dataclass
class PendingConfirmation:
    action_name: str
    params: dict
    target: dict
    previous_grade: Optional[int]


@dataclass
class PipelineResult:
    recognized_text: str = ""
    is_addressed: bool = False
    intent: Intent = field(default_factory=lambda: Intent())
    intents: list[Intent] = field(default_factory=list)
    validation: Optional[ValidationResult] = None
    action_result: Optional[ActionResult] = None
    final_speech: str = ""


@dataclass
class _RuntimeComponents:
    stt: STTEngine
    intent_parser: IntentParser
    response_gen: ResponseGenerator
    tts: TTSEngine


class AssistantCore:
    def __init__(
        self,
        stt: STTEngine,
        wake: WakeDetector,
        intent_parser: IntentParser,
        response_gen: ResponseGenerator,
        actions: ActionRegistry,
        tts: TTSEngine,
        confirmation_parser: ConfirmationParser,
        context: Optional[ActionContext] = None,
    ):
        self.wake = wake
        self.actions = actions
        self.confirmation_parser = confirmation_parser
        self.context = context or ActionContext()
        self.pending_confirmation: Optional[PendingConfirmation] = None

        self._runtime = _RuntimeComponents(
            stt=stt,
            intent_parser=intent_parser,
            response_gen=response_gen,
            tts=tts,
        )

    @property
    def stt(self) -> STTEngine:
        return self._runtime.stt

    @property
    def intent_parser(self) -> IntentParser:
        return self._runtime.intent_parser

    @property
    def response_gen(self) -> ResponseGenerator:
        return self._runtime.response_gen

    @property
    def tts(self) -> TTSEngine:
        return self._runtime.tts

    def replace_runtime_components(self, components: dict) -> None:
        current = self._runtime
        self._runtime = _RuntimeComponents(
            stt=components.get("stt", current.stt),
            intent_parser=components.get("intent_parser", current.intent_parser),
            response_gen=components.get("response_gen", current.response_gen),
            tts=components.get("tts", current.tts),
        )

    # ---------------------------------------------------------------
    # Основной вход
    # ---------------------------------------------------------------
    def handle_audio(
        self,
        audio,
        sample_rate: int,
        on_state: Optional[Callable[[str], None]] = None,
    ) -> PipelineResult:
        rt = self._runtime

        def state(s: str) -> None:
            if on_state:
                on_state(s)

        result = PipelineResult()

        print(
            f"[CORE] handle_audio ENTER "
            f"thread={threading.current_thread().name} "
            f"id={threading.get_ident()}",
            flush=True,
        )

        state("Слушаю")
        state("Распознаю")
        result.recognized_text = rt.stt.transcribe(audio, sample_rate)

        if result.recognized_text:
            print(f"[USER] {result.recognized_text}", flush=True)

        state("Обрабатываю")

        if self.pending_confirmation is not None:
            self._handle_confirmation(result, state, rt)
            state("Ожидание")
            return result

        print("[CORE] before wake.detect", flush=True)
        try:
            wake = self.wake.detect(result.recognized_text)
        except Exception:
            print("[CORE] exception in wake.detect:", flush=True)
            traceback.print_exc()
            raise

        print(
            f"[CORE] wake result: is_addressed={wake.is_addressed} "
            f"cleaned={wake.cleaned_text!r}",
            flush=True,
        )

        result.is_addressed = wake.is_addressed
        self.context.addressed_to_assistant = result.is_addressed

        if not result.is_addressed:
            print("[CORE] not addressed, skipping parse", flush=True)
            state("Ожидание")
            return result

        print(
            f"[CORE] before parse "
            f"thread={threading.current_thread().name} "
            f"id={threading.get_ident()} "
            f"parser={type(rt.intent_parser).__name__}",
            flush=True,
        )
        try:
            result.intents = rt.intent_parser.parse(wake.cleaned_text)
        except Exception:
            print("[CORE] exception in intent_parser.parse:", flush=True)
            traceback.print_exc()
            raise

        print("[CORE] after parse", flush=True)

        for it in result.intents:
            print(f"[INTENT] {it.name} {it.params}", flush=True)

        self._dispatch_intents(result, state, rt)
        state("Ожидание")
        return result

    # ---------------------------------------------------------------
    # Dispatch
    # ---------------------------------------------------------------
    def _dispatch_intents(
        self,
        result: PipelineResult,
        state: Callable[[str], None],
        rt: _RuntimeComponents,
    ) -> None:
        if not result.intents:
            return

        result.intent = result.intents[0]

        if len(result.intents) == 1 and result.intents[0].name == "unknown":
            result.final_speech = (
                "Извините, я не поняла запрос. Уточните, пожалуйста."
            )
            self._emit_llm(result.final_speech)
            self._speak(result.final_speech, state, rt)
            return

        if len(result.intents) == 1 and not result.intents[0].is_action():
            intent = result.intents[0]
            speech = rt.response_gen.generate(
                intent.raw_text or "",
                intent,
                action_result=None,
            )
            result.final_speech = speech
            self._emit_llm(speech)
            self._speak(speech, state, rt)
            return

        collected: list[str] = []
        stop_on_confirmation = False

        for intent in result.intents:
            if stop_on_confirmation:
                break

            action_result, validation = self.actions.dispatch(intent, self.context)
            result.validation = validation
            result.action_result = action_result

            if validation is not None and not validation.allowed:
                collected.append(
                    validation.clarification
                    or validation.reason
                    or "Не могу выполнить это действие."
                )
                continue

            if action_result is None:
                collected.append(rt.response_gen.generate(
                    intent.raw_text or "", intent, action_result=None,
                ))
                continue

            if action_result.needs_confirmation:
                self.pending_confirmation = PendingConfirmation(
                    action_name=intent.name,
                    params=dict(intent.params or {}),
                    target=dict(action_result.details.get("target") or {}),
                    previous_grade=action_result.details.get("current_grade"),
                )
                stop_on_confirmation = True

            collected.append(action_result.message)

        final = " ".join(s for s in collected if s).strip()
        result.final_speech = final
        self._emit_llm(final)
        if final:
            self._speak(final, state, rt)

    # ---------------------------------------------------------------
    # Подтверждение
    # ---------------------------------------------------------------
    def _handle_confirmation(
        self,
        result: PipelineResult,
        state: Callable[[str], None],
        rt: _RuntimeComponents,
    ) -> None:
        decision = self.confirmation_parser.parse(result.recognized_text)

        if decision == ConfirmationDecision.NO:
            self.pending_confirmation = None
            result.final_speech = "Хорошо, отменяю."
            self._emit_llm(result.final_speech)
            self._speak(result.final_speech, state, rt)
            return

        if decision == ConfirmationDecision.UNKNOWN:
            result.final_speech = (
                "Не понял подтверждение. Скажите «да» для выполнения "
                "или «нет» для отмены."
            )
            self._emit_llm(result.final_speech)
            self._speak(result.final_speech, state, rt)
            return

        self._execute_pending(result, state, rt)

    # ---------------------------------------------------------------
    # Выполнение ожидающего действия
    # ---------------------------------------------------------------
    def _execute_pending(
        self,
        result: PipelineResult,
        state: Callable[[str], None],
        rt: _RuntimeComponents,
    ) -> None:
        pending = self.pending_confirmation
        if pending is None:
            return

        if pending.action_name != "grade_student":
            self.pending_confirmation = None
            result.final_speech = (
                "Подтверждение для этого действия пока не поддерживается."
            )
            self._emit_llm(result.final_speech)
            self._speak(result.final_speech, state, rt)
            return

        gb = self._reload_gradebook()
        if gb is None:
            self.pending_confirmation = None
            result.final_speech = "Журнал недоступен, отменяю."
            self._emit_llm(result.final_speech)
            self._speak(result.final_speech, state, rt)
            return

        student_name = pending.params.get("student")
        grade = pending.params.get("grade")
        subject = self.context.current_subject
        lesson = self.context.current_lesson

        if not student_name or grade not in (2, 3, 4, 5) or not subject or not lesson:
            self.pending_confirmation = None
            result.final_speech = "Данные для записи неполные, отменяю."
            self._emit_llm(result.final_speech)
            self._speak(result.final_speech, state, rt)
            return

        matches = gb.find_student(student_name)
        if len(matches) != 1:
            self.pending_confirmation = None
            result.final_speech = (
                "Пока вы подтверждали, журнал изменился: ученик больше "
                "не найден однозначно. Ничего не меняю."
            )
            self._emit_llm(result.final_speech)
            self._speak(result.final_speech, state, rt)
            return

        student_match = matches[0]
        grade_target = gb.find_grade_target(student_match, subject, lesson)
        if grade_target is None:
            self.pending_confirmation = None
            result.final_speech = (
                f"Сегодняшняя дата {lesson} не найдена в журнале. "
                f"Я ничего не меняю."
            )
            self._emit_llm(result.final_speech)
            self._speak(result.final_speech, state, rt)
            return

        current_now = gb.get_grade(grade_target)

        if current_now != pending.previous_grade:
            new_target = {
                "student": grade_target.student,
                "sheet": grade_target.sheet,
                "row": grade_target.row,
                "column": grade_target.column,
                "cell": grade_target.cell,
            }
            self.pending_confirmation = PendingConfirmation(
                action_name=pending.action_name,
                params=pending.params,
                target=new_target,
                previous_grade=current_now,
            )
            if current_now is None:
                result.final_speech = (
                    f"Пока вы подтверждали, ячейка {grade_target.cell} стала пустой. "
                    f"Поставить {grade}?"
                )
            else:
                result.final_speech = (
                    f"Пока вы подтверждали, в ячейке {grade_target.cell} "
                    f"уже появилась оценка {current_now}. Заменить её на {grade}?"
                )
            self._emit_llm(result.final_speech)
            self._speak(result.final_speech, state, rt)
            return

        try:
            print(f"[GRADEBOOK] WRITE sheet={grade_target.sheet} "
                  f"cell={grade_target.cell} grade={grade}", flush=True)
            gb.set_grade(grade_target, grade)
            print(f"[GRADEBOOK] SAVE path={gb.path}", flush=True)
            gb.save()
        except Exception as e:
            print(f"[ERROR] save error: {e}", flush=True)
            self.pending_confirmation = None
            result.final_speech = (
                "Не удалось сохранить оценку в журнале. "
                "Я ничего больше не изменяю."
            )
            self._emit_llm(result.final_speech)
            self._speak(result.final_speech, state, rt)
            return

        verify_gb = self._reload_gradebook()
        if verify_gb is None:
            self.pending_confirmation = None
            result.final_speech = (
                "Не удалось перечитать журнал после сохранения. "
                "Я ничего больше не изменяю."
            )
            self._emit_llm(result.final_speech)
            self._speak(result.final_speech, state, rt)
            return

        verify_target = verify_gb.find_grade_target(student_match, subject, lesson)
        saved_grade = verify_gb.get_grade(verify_target) if verify_target else None

        if verify_target is not None:
            print(f"[GRADEBOOK] VERIFY cell={verify_target.cell} "
                  f"value={saved_grade}", flush=True)

        self.pending_confirmation = None

        if saved_grade != grade:
            result.final_speech = (
                "Не удалось подтвердить запись оценки в журнале. "
                "Я ничего больше не изменяю."
            )
            self._emit_llm(result.final_speech)
            self._speak(result.final_speech, state, rt)
            return

        result.final_speech = (
            f"Готово. {grade_target.student}: оценка {grade} "
            f"за {lesson}."
        )
        self._emit_llm(result.final_speech)
        self._speak(result.final_speech, state, rt)

    # ---------------------------------------------------------------
    # Вспомогательное
    # ---------------------------------------------------------------
    def _reload_gradebook(self) -> Optional[Gradebook]:
        path = self.context.gradebook_path
        if not path:
            return self.context.gradebook

        try:
            from .gradebook import ExcelGradebook
            gb = ExcelGradebook()
            gb.load(path)
            self.context.gradebook = gb
            self.context.known_students = gb.get_students()
            return gb
        except Exception as e:
            print(f"[ERROR] reload gradebook: {e}", flush=True)
            return None

    def _emit_llm(self, text: str) -> None:
        if text:
            print(f"[LLM] {text}", flush=True)

    def _speak(
        self,
        text: str,
        state: Callable[[str], None],
        rt: _RuntimeComponents,
    ) -> None:
        if not text:
            return
        state("Говорю")
        try:
            rt.tts.speak(text)
        except Exception as e:
            print(f"[ERROR] tts: {e}", flush=True)
