"""
Интеграционные тесты: текст → IntentRouter → Intent+params →
Validator → Action.run(params).

Проверяют, что извлечённые параметры реально доходят до Action.

Для open_presentation Action ищет файлы в context.presentations_dir.
Тесты создают временную папку и (при необходимости) файлы.
"""
import os
import sys
from unittest import mock

import numpy as np
import pytest

from assistant.core import AssistantCore
from assistant.wake.keyword_detector import KeywordWakeDetector
from assistant.response.echo_response import EchoResponseGenerator
from assistant.actions.base import (
    ActionRegistry, ActionContext, ActionResult,
)
from assistant.actions.actions_impl import (
    GradeStudentAction, OpenPresentationAction,
    OpenVideoAction, NextSlideAction,
)
from assistant.actions.validators import (
    GradeStudentValidator, OpenPresentationValidator,
    OpenVideoValidator, NextSlideValidator,
)
from assistant.confirmation import KeywordConfirmationParser
from assistant.intent.router.embedding_router import EmbeddingRouter
from assistant.intent.router.fusion import IntentFusion
from assistant.intent.router.llm_router import LLMIntentRouter
from assistant.intent.router.ml_classifier import MLIntentClassifier
from assistant.intent.router.router import IntentRouter


class FakeEmbeddingProvider:
    def __init__(self, dim=8):
        self._dim = dim

    def embed(self, texts, role="passage"):
        out = []
        for t in texts:
            low = (t or "").lower()
            v = np.zeros(self._dim, dtype="float32")

            if "видео" in low or "ролик" in low or "видеозапис" in low:
                v[0] = 1.0
            elif ("следующ" in low
                  or "дальше" in low
                  or "переключи слайд" in low):
                v[3] = 1.0
            elif "презентац" in low or "слайд" in low:
                v[1] = 1.0
            elif any(s in low for s in ("иванов", "сидоров", "петров", "смирнов")):
                v[2] = 1.0
            elif any(w in low for w in ("плюс", "минус", "умножить", "сколько", "раздел")):
                v[4] = 1.0
            elif any(w in low for w in ("привет", "как дела", "здравствуй")):
                v[5] = 1.0

            n = float(np.linalg.norm(v))
            if n > 0:
                v = v / n
            out.append(v.tolist())
        return out

    @property
    def dimension(self):
        return self._dim


class UncertainEmbeddingProvider:
    def __init__(self, dim=8):
        self._dim = dim

    def embed(self, texts, role="passage"):
        return [np.zeros(self._dim, dtype="float32").tolist() for _ in texts]

    @property
    def dimension(self):
        return self._dim


class FakeLLM:
    def __init__(self, responses=None):
        self._responses = list(responses or [])
        self.calls = 0

    def chat(self, user_message, system_prompt=None):
        self.calls += 1
        if not self._responses:
            return '{"intent": "unknown", "confidence": 0.1, "params": {}}'
        return self._responses.pop(0)

    def name(self):
        return "fake"


class FakeSTT:
    def __init__(self):
        self.text = ""

    def transcribe(self, audio, sample_rate):
        return self.text


class SilentTTS:
    def __init__(self):
        self.spoken = []

    def speak(self, text):
        if text:
            self.spoken.append(text)


EXAMPLES = {
    "open_video": [
        "включи видео", "покажи видео", "запусти ролик",
        "включи видеозапись", "открой видео",
    ],
    "open_presentation": [
        "открой презентацию", "покажи презентацию",
        "открой слайды", "покажи слайды",
    ],
    "grade_student": [
        "поставь Иванову четыре", "поставь Сидорову три",
        "Иванов пять", "Сидоров два",
    ],
    "next_slide": ["следующий слайд", "дальше"],
    "answer": [
        "привет", "как дела",
        "сколько будет два плюс два", "сколько будет 25 умножить на 4",
    ],
}


def _make_router_and_llm(llm_responses=None, threshold=0.6):
    llm = FakeLLM(llm_responses)
    router = IntentRouter(
        embedding_router=EmbeddingRouter(EXAMPLES, FakeEmbeddingProvider(),
                                         min_score=0.3),
        ml_classifier=MLIntentClassifier(EXAMPLES, min_confidence=0.1),
        fusion=IntentFusion(min_individual=0.5, agree_bonus=0.05),
        llm_router=LLMIntentRouter(llm),
        confidence_threshold=threshold,
    )
    return router, llm


def _make_core(llm_responses=None, gradebook=None, presentations_dir=None):
    router, llm = _make_router_and_llm(llm_responses)

    reg = ActionRegistry()
    reg.register(GradeStudentAction(), GradeStudentValidator())
    reg.register(OpenPresentationAction(), OpenPresentationValidator())
    reg.register(OpenVideoAction(), OpenVideoValidator())
    reg.register(NextSlideAction(), NextSlideValidator())

    ctx = ActionContext(
        addressed_to_assistant=True,
        current_subject="Электроснабжение",
        current_lesson="17.09",
        gradebook=gradebook,
        gradebook_path=None,
        known_students=[],
        dry_run=False,
        presentations_dir=presentations_dir,
        presentation_match_threshold=0.70,
        presentation_ambiguity_margin=0.05,
    )

    stt = FakeSTT()
    tts = SilentTTS()
    core = AssistantCore(
        stt=stt,
        wake=KeywordWakeDetector(aliases=["ассистент"]),
        intent_parser=router,
        response_gen=EchoResponseGenerator(),
        actions=reg,
        tts=tts,
        confirmation_parser=KeywordConfirmationParser(),
        context=ctx,
    )
    return core, stt, tts, router, llm


def _run(core, stt, text):
    stt.text = text
    return core.handle_audio(np.zeros(16000, dtype="float32"), 16000)


# ---------------------------------------------------------------------------
# 1. open_video: topic доходит до Action.details
# ---------------------------------------------------------------------------

def test_open_video_topic_reaches_action():
    core, stt, tts, router, llm = _make_core()
    r = _run(core, stt, "Ассистент, включи видео про электричество")

    assert r.intent.name == "open_video"
    assert r.intent.params.get("topic") == "электричество"

    assert r.action_result is not None
    assert r.action_result.details.get("topic") == "электричество"
    assert llm.calls == 0


# ---------------------------------------------------------------------------
# 2. open_presentation: topic доходит до Action
# ---------------------------------------------------------------------------

def test_open_presentation_topic_reaches_action(tmp_path):
    # Создаём файл, точно совпадающий по имени с извлечённой темой.
    # extractor даёт topic="физике", файл "Физике.pptx" → exact.
    (tmp_path / "Физике.pptx").write_bytes(b"fake")

    core, stt, tts, router, llm = _make_core(presentations_dir=str(tmp_path))

    with mock.patch("assistant.actions.actions_impl._open_file",
                    return_value=True):
        r = _run(core, stt, "Ассистент, открой презентацию по физике")

    assert r.intent.name == "open_presentation"
    assert r.intent.params.get("topic") == "физике"

    assert r.action_result is not None
    assert r.action_result.executed is True
    assert r.action_result.details.get("topic") == "физике"
    assert llm.calls == 0


# ---------------------------------------------------------------------------
# 3. open_video без topic
# ---------------------------------------------------------------------------

def test_open_video_without_topic_passes_empty():
    core, stt, tts, router, llm = _make_core()
    r = _run(core, stt, "Ассистент, включи видео")

    assert r.intent.name == "open_video"
    assert r.intent.params == {}

    assert r.action_result is not None
    assert r.action_result.details.get("topic") == ""
    assert llm.calls == 0


def test_open_presentation_without_topic_passes_empty(tmp_path):
    core, stt, tts, router, llm = _make_core(presentations_dir=str(tmp_path))
    r = _run(core, stt, "Ассистент, открой презентацию")

    assert r.intent.name == "open_presentation"
    assert r.intent.params == {}

    # Action вернёт no_topic.
    assert r.action_result is not None
    assert r.action_result.executed is False
    assert r.action_result.details.get("reason") == "no_topic"
    assert llm.calls == 0


# ---------------------------------------------------------------------------
# 4. grade_student: params доходят до Action.run
# ---------------------------------------------------------------------------

class FakeGradebook:
    def __init__(self):
        from assistant.gradebook.base import StudentMatch, GradeTarget
        self._StudentMatch = StudentMatch
        self._GradeTarget = GradeTarget

    def get_students(self):
        return ["Иванов Пётр Сергеевич"]

    def find_student(self, name):
        if "иванов" in (name or "").lower():
            return [self._StudentMatch(
                full_name="Иванов Пётр Сергеевич",
                row=2,
                sheet="Электроснабжение",
            )]
        return []

    def find_grade_target(self, student, subject, lesson):
        return self._GradeTarget(
            student=student.full_name,
            sheet=subject,
            row=student.row,
            column="F",
            cell="F2",
        )

    def get_grade(self, target):
        return None

    def set_grade(self, target, grade):
        pass

    def save(self):
        pass

    def load(self, path):
        pass


def test_grade_student_params_reach_action():
    core, stt, tts, router, llm = _make_core(gradebook=FakeGradebook())

    captured = {}
    original_run = GradeStudentAction.run

    def spy_run(self, params, context, target=None, current_grade=None):
        captured["params"] = dict(params or {})
        captured["target"] = dict(target or {})
        captured["current_grade"] = current_grade
        return ActionResult(
            executed=False,
            needs_confirmation=True,
            dry_run=True,
            message="[spy] план готов",
            details={"target": target or {}, "current_grade": current_grade},
        )

    GradeStudentAction.run = spy_run
    try:
        r = _run(core, stt, "Ассистент, поставь Иванову четыре")

        assert r.intent.name == "grade_student"
        assert r.intent.params.get("student") == "Иванову"
        assert r.intent.params.get("grade") == 4

        assert captured.get("params"), "GradeStudentAction.run не был вызван"
        assert captured["params"].get("student") == "Иванов Пётр Сергеевич"
        assert captured["params"].get("grade") == 4
        assert captured["target"].get("cell") == "F2"

        assert llm.calls == 0
    finally:
        GradeStudentAction.run = original_run


# ---------------------------------------------------------------------------
# 5. LLM fallback: params уже от LLM — extractor не перезаписывает
# ---------------------------------------------------------------------------

def test_llm_params_are_not_overwritten_by_extractor():
    llm_responses = [
        '{"intent": "open_video", "confidence": 0.95, '
        '"params": {"topic": "трансформаторы"}}',
    ]
    llm = FakeLLM(llm_responses)
    router = IntentRouter(
        embedding_router=EmbeddingRouter(EXAMPLES, UncertainEmbeddingProvider(),
                                         min_score=0.3),
        ml_classifier=MLIntentClassifier(EXAMPLES, min_confidence=0.99),
        fusion=IntentFusion(min_individual=0.5),
        llm_router=LLMIntentRouter(llm),
        confidence_threshold=0.75,
    )

    decision = router.route("включи видео про электричество")

    assert decision.used_llm is True
    assert llm.calls == 1
    assert decision.intent.name == "open_video"
    assert decision.intent.params.get("topic") == "трансформаторы"


# ---------------------------------------------------------------------------
# 6. LLM fallback: params пусты — локальный extractor добирает
# ---------------------------------------------------------------------------

def test_llm_empty_params_falls_back_to_local_extractor():
    llm_responses = [
        '{"intent": "open_video", "confidence": 0.95, "params": {}}',
    ]
    llm = FakeLLM(llm_responses)
    router = IntentRouter(
        embedding_router=EmbeddingRouter(EXAMPLES, UncertainEmbeddingProvider(),
                                         min_score=0.3),
        ml_classifier=MLIntentClassifier(EXAMPLES, min_confidence=0.99),
        fusion=IntentFusion(min_individual=0.5),
        llm_router=LLMIntentRouter(llm),
        confidence_threshold=0.75,
    )

    decision = router.route("включи видео про трансформаторы")

    assert decision.used_llm is True
    assert llm.calls == 1
    assert decision.intent.name == "open_video"
    assert decision.intent.params.get("topic") == "трансформаторы"


# ---------------------------------------------------------------------------
# 7. Локальные сценарии не вызывают LLM
# ---------------------------------------------------------------------------

def test_local_scenarios_do_not_call_llm(tmp_path):
    core, stt, tts, router, llm = _make_core(presentations_dir=str(tmp_path))

    for text in (
        "Ассистент, включи видео про электричество",
        "Ассистент, следующий слайд",
    ):
        _run(core, stt, text)

    assert llm.calls == 0


# ---------------------------------------------------------------------------
# 8. unknown не идёт в Action
# ---------------------------------------------------------------------------

def test_unknown_does_not_reach_action():
    llm_responses = [
        '{"intent": "open_video", "confidence": 0.1, "params": {}}',
    ]
    core, stt, tts, router, llm = _make_core(llm_responses)

    r = _run(core, stt, "Ассистент, абсолютно непонятная команда")

    assert r.intent.name == "unknown"
    assert r.action_result is None
    assert r.validation is None
    assert ("не поняла" in r.final_speech.lower()
            or "уточните" in r.final_speech.lower())


def run_all():
    print("Запуск через pytest: pytest -v tools/test_pipeline_params_to_action.py",
          flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(run_all())
