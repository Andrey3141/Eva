from .base import ResponseGenerator
from ..intent.base import Intent


class EchoResponseGenerator(ResponseGenerator):
    """
    Офлайн-шаблоны для ветки answer.
    Для действий используется ActionResult.message — сюда не попадает.
    """

    def generate(
        self,
        user_command: str,
        intent: Intent,
        action_result: str | None = None,
    ) -> str:
        params = intent.params or {}

        if intent.name == "grade_student":
            student = params.get("student", "ученику")
            grade = params.get("grade", "?")
            return f"Ставлю {student} оценку {grade}."

        if intent.name == "next_slide":
            return "Перехожу к следующему слайду."

        if intent.name == "answer":
            text = (intent.raw_text or user_command or "").strip()
            return f"Вы сказали: {text}" if text else "Я вас слушаю."

        return action_result or (
            f"Команда распознана как {intent.name}, но действие не поддерживается."
        )
