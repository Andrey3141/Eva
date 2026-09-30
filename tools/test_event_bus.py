"""
Тесты EventBus.

Запуск через pytest:
    pytest -v tools/test_event_bus.py
Прямой запуск:
    python -m tools.test_event_bus
"""
import sys
import threading

from assistant.events import EventBus, Event, EventType


def test_subscribe_and_publish():
    bus = EventBus()
    seen = []
    bus.subscribe(EventType.USER_MESSAGE, lambda e: seen.append(e.payload))
    bus.publish(Event(type=EventType.USER_MESSAGE, payload={"text": "привет"}))
    assert len(seen) == 1
    assert seen[0]["text"] == "привет"


def test_multiple_subscribers():
    bus = EventBus()
    a, b, c = [], [], []
    bus.subscribe(EventType.USER_MESSAGE, lambda e: a.append(e))
    bus.subscribe(EventType.USER_MESSAGE, lambda e: b.append(e))
    bus.subscribe(EventType.USER_MESSAGE, lambda e: c.append(e))
    bus.publish(Event(type=EventType.USER_MESSAGE, payload={"text": "x"}))
    assert len(a) == len(b) == len(c) == 1


def test_unsubscribe():
    bus = EventBus()
    seen = []
    handler = lambda e: seen.append(e)

    bus.subscribe(EventType.USER_MESSAGE, handler)
    bus.publish(Event(type=EventType.USER_MESSAGE, payload={"text": "1"}))
    bus.unsubscribe(EventType.USER_MESSAGE, handler)
    bus.publish(Event(type=EventType.USER_MESSAGE, payload={"text": "2"}))

    assert len(seen) == 1, len(seen)
    assert seen[0].payload["text"] == "1"


def test_unsubscribe_unknown_handler_does_not_fail():
    bus = EventBus()
    handler = lambda e: None
    bus.unsubscribe(EventType.USER_MESSAGE, handler)  # не должно падать


def test_publish_unknown_type_does_not_fail():
    bus = EventBus()
    bus.publish(Event(type=EventType.LISTENING_FINISHED, payload={}))


def test_handler_exception_does_not_break_others():
    """
    Ошибка одного подписчика не должна мешать остальным.
    Это соответствует текущей реализации EventBus.publish.
    """
    bus = EventBus()
    seen = []

    def broken(e):
        raise RuntimeError("boom")

    bus.subscribe(EventType.USER_MESSAGE, broken)
    bus.subscribe(EventType.USER_MESSAGE, lambda e: seen.append(e))

    bus.publish(Event(type=EventType.USER_MESSAGE, payload={"text": "ok"}))
    assert len(seen) == 1, "здоровый подписчик не получил событие"


def test_subscribe_from_multiple_threads():
    bus = EventBus()
    seen = []
    lock = threading.Lock()

    def h(e):
        with lock:
            seen.append(e)

    bus.subscribe(EventType.USER_MESSAGE, h)

    def worker(i):
        bus.publish(Event(type=EventType.USER_MESSAGE, payload={"i": i}))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(seen) == 20, len(seen)


def run_all():
    tests = [
        test_subscribe_and_publish,
        test_multiple_subscribers,
        test_unsubscribe,
        test_unsubscribe_unknown_handler_does_not_fail,
        test_publish_unknown_type_does_not_fail,
        test_handler_exception_does_not_break_others,
        test_subscribe_from_multiple_threads,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"[OK] {t.__name__}", flush=True)
        except AssertionError as e:
            failed += 1
            print(f"[FAIL] {t.__name__}: {e}", flush=True)
        except Exception as e:
            failed += 1
            print(f"[ERROR] {t.__name__}: {type(e).__name__}: {e}", flush=True)
    print(flush=True)
    print(f"=== {len(tests) - failed}/{len(tests)} EVENT BUS TESTS PASSED ===", flush=True)
    return failed


def main():
    import os
    if not os.path.exists("assistant"):
        print("Запускать из корня проекта.", flush=True)
        sys.exit(2)
    sys.exit(1 if run_all() else 0)


if __name__ == "__main__":
    main()
