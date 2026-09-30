"""
КастылиParameterRouter — простая реализация извлечения параметров.

Совместим по интерфейсу с ParameterRouter.extract_params():
возвращает (params, accepted, rejected, debug).
accepted/rejected здесь пусты — это заглушка для совместимости;
контракт с IntentRouter сохраняется.
"""
from __future__ import annotations

from . import grade as _grade
from . import presentation as _presentation
from . import video as _video


class КастылиParameterRouter:
    def extract_params(self, text: str, intent_name: str):
        params: dict = {}

        if intent_name == "open_presentation":
            params = _presentation.extract_topic(text)
        elif intent_name == "open_video":
            params = _video.extract_topic(text)
        elif intent_name == "grade_student":
            params = _grade.extract_params(text)
        # next_slide, answer → {}

        print(
            f"[PARAMETER_ROUTER] mode=кастыли intent={intent_name!r} "
            f"params={params!r}",
            flush=True,
        )

        return params, [], [], {"mode": "кастыли"}

    def extract(self, text, intent):
        params, _, _, _ = self.extract_params(text, intent.name)
        from dataclasses import dataclass
        from assistant.intent.parameter.types import ParameterPrediction

        @dataclass
        class _Result:
            params: dict
            accepted: list
            rejected: list
            debug: dict

        return _Result(params=params, accepted=[], rejected=[],
                       debug={"mode": "кастыли"})
