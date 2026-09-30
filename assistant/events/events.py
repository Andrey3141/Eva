from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EventType(str, Enum):
    ASSISTANT_STATE_CHANGED = "assistant_state_changed"

    USER_MESSAGE = "user_message"
    ASSISTANT_MESSAGE = "assistant_message"

    TTS_STARTED = "tts_started"
    TTS_FINISHED = "tts_finished"

    ACTION_REQUESTED = "action_requested"
    ACTION_COMPLETED = "action_completed"
    CONFIRMATION_REQUIRED = "confirmation_required"

    AUDIO_WARNING = "audio_warning"

    ERROR = "error"

    LISTENING_STARTED = "listening_started"
    LISTENING_FINISHED = "listening_finished"

    # --- новые ---
    MICROPHONE_MUTED_CHANGED = "microphone_muted_changed"
    CONFIG_CHANGED = "config_changed"


@dataclass
class Event:
    type: EventType
    payload: dict[str, Any] = field(default_factory=dict)
