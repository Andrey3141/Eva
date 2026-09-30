"""
Integration-тест EVA pipeline без сети:
    STT(scripted) → Wake → Intent(echo) → Action(dry) → Response(echo) → TTS(silent)

Запуск:
    python -m tools.test_integration_pipeline
"""
from __future__ import annotations

import sys

import numpy as np

from assistant.logging_setup import setup_logging, get_logger

setup_logging(level="INFO", to_console=True)
log = get_logger("integration")


class ScriptedSTT:
    def __init__(self):
        self.next_text = ""

    def transcribe(self, audio, sample_rate) -> str:
        return self.next_text


class SilentTTS:
    def __init__(self):
        self.spoken: list[str] = []

    def speak(self, text: str) -> None:
        self.spoken.append(text)
        log.info("TTS spoke: %r", text)


def main() -> int:
    print("=== EVA INTEGRATION PIPELINE ===", flush=True)

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
    from assistant.confirmation import KeywordConfirmationParser

    stt = ScriptedSTT()
    tts = SilentTTS()

    reg = ActionRegistry()
    reg.register(GradeStudentAction(), GradeStudentValidator())
    reg.register(OpenPresentationAction(), OpenPresentationValidator())
    reg.register(OpenVideoAction(), OpenVideoValidator())
    reg.register(NextSlideAction(), NextSlideValidator())

    ctx = ActionContext(addressed_to_assistant=False, dry_run=True)

    core = AssistantCore(
        stt=stt,
        wake=KeywordWakeDetector(),
        intent_parser=EchoIntentParser(),
        response_gen=EchoResponseGenerator(),
        actions=reg,
        tts=tts,
        confirmation_parser=KeywordConfirmationParser(),
        context=ctx,
    )

    # 1. Обычный вопрос
    stt.next_text = "Ассистент, привет"
    r1 = core.handle_audio(np.zeros(16000, dtype="float32"), 16000)
    assert r1.is_addressed is True
    assert "Вы сказали: привет" in r1.final_speech, r1.final_speech
    log.info("case 1 OK: %r", r1.final_speech)

    # 2. Не обращение
    stt.next_text = "Сидоров завтра будет"
    r2 = core.handle_audio(np.zeros(16000, dtype="float32"), 16000)
    assert r2.is_addressed is False
    log.info("case 2 OK: ignored")

    # 3. Команда — оценка (dry-run)
    stt.next_text = "Ассистент, Сидорову 2"
    r3 = core.handle_audio(np.zeros(16000, dtype="float32"), 16000)
    assert r3.is_addressed is True
    assert "grade_student" in r3.intent.name
    log.info("case 3 OK: intent=%s", r3.intent.name)

    print("=== INTEGRATION OK ===", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
