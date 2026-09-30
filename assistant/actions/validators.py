from .base import ActionValidator, ActionContext, ValidationResult
from ..intent.base import Intent


class GradeStudentValidator(ActionValidator):
    MIN_CONFIDENCE = 0.75

    def validate(self, intent: Intent, context: ActionContext) -> ValidationResult:
        if not context.addressed_to_assistant:
            return ValidationResult(False, "Команда не адресована ассистенту.")
        if intent.confidence < self.MIN_CONFIDENCE:
            return ValidationResult(
                False,
                "Слишком низкая уверенность распознавания намерения.",
                clarification="Уточните, пожалуйста, что нужно сделать.",
            )

        missing = []
        student_raw = (intent.params.get("student") or "").strip()
        grade = intent.params.get("grade")
        if not student_raw:
            missing.append("student")
        if grade not in (2, 3, 4, 5):
            missing.append("grade")
        if missing:
            return ValidationResult(
                False,
                "Не хватает параметров для выставления оценки.",
                missing=missing,
                clarification="Уточните, пожалуйста, ученика и оценку.",
            )

        if not context.gradebook_available:
            return ValidationResult(
                False,
                "Журнал не подключён.",
                clarification="Журнал пока не подключён. Работаю в тестовом режиме.",
                normalized_params={"student": student_raw, "grade": grade},
            )

        matches = context.gradebook.find_student(student_raw)
        if len(matches) == 0:
            return ValidationResult(
                False,
                f"Ученик «{student_raw}» не найден в журнале.",
                clarification=f"Я не нашла ученика «{student_raw}». Повторите, пожалуйста.",
            )
        if len(matches) > 1:
            names = ", ".join(m.full_name for m in matches)
            return ValidationResult(
                False,
                f"Найдено несколько совпадений для «{student_raw}».",
                clarification=f"Уточните, пожалуйста: {names}.",
            )

        student_match = matches[0]
        normalized_params = {
            "student": student_match.full_name,
            "grade": grade,
        }

        if not context.current_subject or not context.current_lesson:
            return ValidationResult(
                False,
                "Не определены текущий предмет или занятие.",
                clarification="Не понимаю, к какому занятию отнести оценку.",
                normalized_params=normalized_params,
            )

        grade_target = context.gradebook.find_grade_target(
            student=student_match,
            subject=context.current_subject,
            lesson=context.current_lesson,
        )
        if grade_target is None:
            lesson = context.current_lesson or "?"
            return ValidationResult(
                False,
                f"Колонка с занятием {lesson} не найдена в журнале.",
                clarification=(
                    f"Сегодняшняя дата {lesson} не найдена в журнале. "
                    f"Не могу определить, куда ставить оценку."
                ),
                normalized_params=normalized_params,
            )

        target = {
            "student": grade_target.student,
            "sheet": grade_target.sheet,
            "row": grade_target.row,
            "column": grade_target.column,
            "cell": grade_target.cell,
        }
        current = context.gradebook.get_grade(grade_target)

        return ValidationResult(
            allowed=True,
            reason="Все проверки пройдены.",
            normalized_params=normalized_params,
            target=target,
            current_grade=current,
        )


class OpenFileValidator(ActionValidator):
    MIN_CONFIDENCE = 0.6

    def validate(self, intent: Intent, context: ActionContext) -> ValidationResult:
        if not context.addressed_to_assistant:
            return ValidationResult(False, "Команда не адресована ассистенту.")
        if intent.confidence < self.MIN_CONFIDENCE:
            return ValidationResult(False, "Слишком низкая уверенность.")
        target_name = (intent.params.get("target") or "").strip()
        if not target_name:
            return ValidationResult(
                False,
                "Не указано, что открыть.",
                clarification="Уточните, пожалуйста, что открыть.",
            )
        return ValidationResult(
            True,
            "ОК",
            normalized_params={"target": target_name},
        )


class OpenPresentationValidator(ActionValidator):
    MIN_CONFIDENCE = 0.7

    def validate(self, intent: Intent, context: ActionContext) -> ValidationResult:
        if not context.addressed_to_assistant:
            return ValidationResult(False, "Команда не адресована ассистенту.")
        if intent.confidence < self.MIN_CONFIDENCE:
            return ValidationResult(
                False, "Слишком низкая уверенность.",
                clarification="Уточните, какую презентацию открыть.",
            )
        topic = (intent.params.get("topic") or "").strip()
        return ValidationResult(
            True, "ОК",
            normalized_params={"topic": topic},
        )


class OpenVideoValidator(ActionValidator):
    MIN_CONFIDENCE = 0.7

    def validate(self, intent: Intent, context: ActionContext) -> ValidationResult:
        if not context.addressed_to_assistant:
            return ValidationResult(False, "Команда не адресована ассистенту.")
        if intent.confidence < self.MIN_CONFIDENCE:
            return ValidationResult(
                False, "Слишком низкая уверенность.",
                clarification="Уточните, какое видео включить.",
            )
        topic = (intent.params.get("topic") or "").strip()
        return ValidationResult(
            True, "ОК",
            normalized_params={"topic": topic},
        )


class NextSlideValidator(ActionValidator):
    MIN_CONFIDENCE = 0.8

    def validate(self, intent: Intent, context: ActionContext) -> ValidationResult:
        if not context.addressed_to_assistant:
            return ValidationResult(False, "Команда не адресована ассистенту.")
        if intent.confidence < self.MIN_CONFIDENCE:
            return ValidationResult(False, "Слишком низкая уверенность.")
        return ValidationResult(True, "ОК")


class CloseActionValidator(ActionValidator):
    MIN_CONFIDENCE = 0.6

    def validate(self, intent: Intent, context: ActionContext) -> ValidationResult:
        if not context.addressed_to_assistant:
            return ValidationResult(False, "Команда не адресована ассистенту.")
        if intent.confidence < self.MIN_CONFIDENCE:
            return ValidationResult(
                False,
                "Слишком низкая уверенность.",
                clarification="Уточните, пожалуйста, что закрыть.",
            )
        return ValidationResult(True, "ОК", normalized_params={})


class RestartActionValidator(ActionValidator):
    MIN_CONFIDENCE = 0.6

    def validate(self, intent: Intent, context: ActionContext) -> ValidationResult:
        if not context.addressed_to_assistant:
            return ValidationResult(False, "Команда не адресована ассистенту.")
        if intent.confidence < self.MIN_CONFIDENCE:
            return ValidationResult(
                False,
                "Слишком низкая уверенность.",
                clarification="Уточните, пожалуйста, что переоткрыть.",
            )
        return ValidationResult(True, "ОК", normalized_params={})
