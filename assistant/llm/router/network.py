from __future__ import annotations

import socket
import time
from typing import Optional


class NetworkChecker:
    """
    Простейшая проверка доступности сети.
    Без requests, без внешних библиотек.
    Результат кэшируется на короткий интервал, чтобы не дёргать сеть на каждый запрос.
    """

    def __init__(self, cache_seconds: float = 15.0):
        self._cache_seconds = cache_seconds
        self._last_check: float = 0.0
        self._last_result: Optional[bool] = None

    def is_online(self) -> bool:
        now = time.time()
        if self._last_result is not None and (now - self._last_check) < self._cache_seconds:
            return self._last_result

        result = self._probe()
        self._last_result = result
        self._last_check = now
        return result

    @staticmethod
    def _probe() -> bool:
        # Пробуем TCP-соединение с DNS-серверами и публичными хостами.
        targets = [
            ("1.1.1.1", 53),
            ("8.8.8.8", 53),
            ("api.openai.com", 443),
        ]
        for host, port in targets:
            try:
                sock = socket.create_connection((host, port), timeout=1.5)
                sock.close()
                return True
            except OSError:
                continue
        return False

    def force_refresh(self) -> bool:
        self._last_result = None
        self._last_check = 0.0
        return self.is_online()
