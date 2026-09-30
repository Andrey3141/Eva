from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from ..intent.base import Intent
from ..gradebook.base import Gradebook


@dataclass
class ValidationResult:
    allowed: bool
    reason: str = ""
    missing: list[str] = field(default_factory=list)
    clarification: str = ""

    normalized_params: dict = field(default_factory=dict)
    target: dict = field(default_factory=dict)

    current_grade: Optional[int] = None


@dataclass
class ActionContext:
    addressed_to_assistant: bool = False
    current_subject: Optional[str] = None
    current_lesson: Optional[str] = None
    known_students: list[str] = field(default_factory=list)
    dry_run: bool = True

    gradebook: Optional[Gradebook] = None
    gradebook_path: Optional[str] = None

    presentations_dir: Optional[str] = None
    presentation_match_threshold: float = 0.70
    presentation_ambiguity_margin: float = 0.05

    # Runtime-состояние последнего открытого файла.
    # НЕ persists между запусками. Заполняется только после успешного
    # _open_file(). Очищается только после ПОДТВЕРЖДЁННОГО закрытия.
    last_opened_type: Optional[str] = None   # "presentation"|"video"|"excel"|"file"
    last_opened_path: Optional[str] = None
    last_opened_app: Optional[str] = None    # "powerpoint"|"libreoffice"|"vlc"|"excel"

    @property
    def gradebook_available(self) -> bool:
        return self.gradebook is not None


class ActionValidator(ABC):
    @abstractmethod
    def validate(self, intent: Intent, context: ActionContext) -> ValidationResult:
        ...


@dataclass
class ActionResult:
    executed: bool
    message: str
    needs_confirmation: bool = False
    dry_run: bool = False
    details: dict = field(default_factory=dict)


class BaseAction(ABC):
    name: str = "base"

    @abstractmethod
    def run(
        self,
        params: dict,
        context: ActionContext,
        target: dict | None = None,
        current_grade: Optional[int] = None,
    ) -> ActionResult:
        ...


class ActionRegistry:
    def __init__(self):
        self._actions: dict[str, BaseAction] = {}
        self._validators: dict[str, ActionValidator] = {}

    def register(self, action: BaseAction, validator: ActionValidator):
        self._actions[action.name] = action
        self._validators[action.name] = validator

    def get(self, name: str) -> BaseAction | None:
        return self._actions.get(name)

    def get_validator(self, name: str) -> ActionValidator | None:
        return self._validators.get(name)

    def dispatch(
        self,
        intent: Intent,
        context: ActionContext,
    ) -> tuple[Optional[ActionResult], Optional[ValidationResult]]:
        action = self._actions.get(intent.name)
        if action is None:
            return None, None

        validator = self._validators.get(intent.name)
        if validator is None:
            return None, ValidationResult(
                allowed=False,
                reason=f"Для действия «{intent.name}» не зарегистрирован валидатор.",
            )

        validation = validator.validate(intent, context)
        if not validation.allowed:
            return None, validation

        params = validation.normalized_params or dict(intent.params or {})
        result = action.run(
            params,
            context,
            target=validation.target or {},
            current_grade=validation.current_grade,
        )
        return result, validation
