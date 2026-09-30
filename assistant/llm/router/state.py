from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ProviderStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    COOLDOWN = "COOLDOWN"
    DISABLED = "DISABLED"


class FailureReason(str, Enum):
    NETWORK_OFFLINE = "NETWORK_OFFLINE"
    QUOTA_EXHAUSTED = "QUOTA_EXHAUSTED"
    RATE_LIMITED = "RATE_LIMITED"
    AUTH_ERROR = "AUTH_ERROR"
    TIMEOUT = "TIMEOUT"
    SERVER_ERROR = "SERVER_ERROR"
    INVALID_RESPONSE = "INVALID_RESPONSE"


@dataclass
class ProviderRuntimeState:
    """
    Временное состояние провайдера. Живёт только в текущем запуске EVA.
    Не сериализуется нигде.
    """
    status: ProviderStatus = ProviderStatus.AVAILABLE
    reason: Optional[FailureReason] = None
    cooldown_until: float = 0.0        # UNIX-timestamp, 0 = нет cooldown

    def is_usable(self) -> bool:
        if self.status == ProviderStatus.DISABLED:
            return False
        if self.status == ProviderStatus.COOLDOWN:
            if time.time() >= self.cooldown_until:
                # cooldown истёк — снова AVAILABLE
                self.status = ProviderStatus.AVAILABLE
                self.reason = None
                self.cooldown_until = 0.0
                return True
            return False
        return True

    def disable(self, reason: FailureReason) -> None:
        self.status = ProviderStatus.DISABLED
        self.reason = reason

    def cooldown(self, reason: FailureReason, seconds: float) -> None:
        self.status = ProviderStatus.COOLDOWN
        self.reason = reason
        self.cooldown_until = time.time() + seconds

    def reset(self) -> None:
        self.status = ProviderStatus.AVAILABLE
        self.reason = None
        self.cooldown_until = 0.0
