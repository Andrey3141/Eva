"""
«Кастыли» — отдельный простой fallback-режим извлечения параметров.

Используется, когда ML+Embedding+Fusion ошибается.

Изолирован: не импортирует assistant.intent.parameter.
Возвращает только params (dict), Action занимается выполнением.
"""
from .router import КастылиParameterRouter

__all__ = ["КастылиParameterRouter"]
