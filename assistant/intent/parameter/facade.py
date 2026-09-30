"""
ParameterRouterFacade — выбирает реализацию извлечения параметров
по Config.PARAMETER_ROUTER_MODE.

Значения:
  - "ml"        → существующий ParameterRouter (ML + Embedding + Fusion)
  - "кастыли"   → fallback КастылиParameterRouter
"""
from __future__ import annotations


class ParameterRouterFacade:
    def __init__(self, ml_router, kastyli_router=None):
        self._ml_router = ml_router
        self._kastyli_router = kastyli_router

    def _active(self):
        from config import Config
        mode = (getattr(Config, "PARAMETER_ROUTER_MODE", "ml") or "ml").lower()

        if mode == "кастыли" and self._kastyli_router is not None:
            return self._kastyli_router
        return self._ml_router

    def extract_params(self, text: str, intent_name: str):
        router = self._active()
        if router is None:
            return {}, [], [], {"mode": "none"}
        return router.extract_params(text, intent_name)

    def extract(self, text, intent):
        router = self._active()
        if router is None:
            from .types import ParameterRouterResult  # may not exist
            return None
        return router.extract(text, intent)
