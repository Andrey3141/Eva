import threading
from collections import defaultdict
from typing import Callable

from .events import Event, EventType


class EventBus:
    """
    Простая потокобезопасная шина событий.
    Публикация не блокирует подписчиков надолго — обработчики должны
    сами решать, в каком потоке им выполняться (UI-поток через Qt-сигналы).
    """

    def __init__(self) -> None:
        self._subs: dict[EventType, list[Callable[[Event], None]]] = defaultdict(list)
        self._lock = threading.Lock()

    def subscribe(self, event_type: EventType, handler: Callable[[Event], None]) -> None:
        with self._lock:
            self._subs[event_type].append(handler)

    def unsubscribe(self, event_type: EventType, handler: Callable[[Event], None]) -> None:
        with self._lock:
            if handler in self._subs[event_type]:
                self._subs[event_type].remove(handler)

    def publish(self, event: Event) -> None:
        with self._lock:
            handlers = list(self._subs.get(event.type, []))

        for h in handlers:
            try:
                h(event)
            except Exception as e:
                # Падение подписчика не должно ронять публикацию.
                print(f"[EventBus] handler error for {event.type}: {e}")
