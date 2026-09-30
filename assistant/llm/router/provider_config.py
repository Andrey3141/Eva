from __future__ import annotations

from dataclasses import dataclass


@dataclass
class LLMProviderConfig:
    name: str
    model: str
    priority: int
    requires_internet: bool = True
    supports_intent: bool = True
    supports_response: bool = True
    supports_json: bool = True
    timeout: float = 10.0
    max_retries: int = 1
