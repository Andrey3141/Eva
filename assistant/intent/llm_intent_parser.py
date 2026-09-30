import json
import re

from .base import Intent, IntentParser
from ..llm.base import LLMEngine


SYSTEM_PROMPT = """\
Ты — модуль разбора намерений голосового ассистента преподавателя.
На вход приходит фраза пользователя. Верни СТРОГО JSON-МАССИВ намерений.

Формат одного элемента:
{
  "intent": "<grade_student | open_file | next_slide | answer>",
  "params": { ... },
  "confidence": <число от 0.0 до 1.0>
}

Примеры params:
- grade_student: {"student": "Сидорову", "grade": 2}
- open_file:     {"target": "таблицу"}
- next_slide:    {}
- answer:        {}

Правила:
- Если это вопрос или обычная речь — [{"intent": "answer", "params": {}, "confidence": 0.9}].
- Если фраза содержит несколько независимых действий — верни массив из нескольких элементов.
- Никаких пояснений, только JSON.
"""


class LLMIntentParser(IntentParser):
    def __init__(self, llm: LLMEngine):
        self.llm = llm

    def parse(self, user_command: str) -> list[Intent]:
        raw = self.llm.chat(user_command, SYSTEM_PROMPT)
        data = self._extract_json(raw)

        if data is None:
            return [Intent(name="answer", params={}, confidence=0.5, raw_text=raw)]

        if isinstance(data, dict):
            data = [data]
        if not isinstance(data, list):
            return [Intent(name="answer", params={}, confidence=0.5, raw_text=raw)]

        out: list[Intent] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            out.append(Intent(
                name=str(item.get("intent", "unknown")),
                params=item.get("params", {}) or {},
                confidence=float(item.get("confidence", 0.0) or 0.0),
                raw_text=user_command,
            ))

        return out or [Intent(name="answer", params={}, confidence=0.5, raw_text=user_command)]

    @staticmethod
    def _extract_json(text: str):
        m = re.search(r"(\[.*\]|\{.*\})", text or "", re.DOTALL)
        if not m:
            return None
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
