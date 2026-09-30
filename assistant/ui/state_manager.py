from enum import Enum
from typing import Callable

from ..events import EventBus, Event, EventType


class AssistantState(str, Enum):
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    WAITING_CONFIRMATION = "waiting_confirmation"
    ERROR = "error"


class StateManager:
    """
    Хранит текущее состояние ассистента и публикует событие
    ASSISTANT_STATE_CHANGED при каждом изменении.
    """

    def __init__(self, bus: EventBus):
        self.bus = bus
        self._state = AssistantState.IDLE

    @property
    def state(self) -> AssistantState:
        return self._state

    def set(self, state: AssistantState) -> None:
        if state == self._state:
            return
        self._state = state
        self.bus.publish(Event(
            type=EventType.ASSISTANT_STATE_CHANGED,
            payload={"state": state},
        ))
