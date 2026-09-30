"""
Тесты SettingsStore и применения настроек к Config.

Запуск:
    pytest -v tools/test_settings_store.py
    python -m tools.test_settings_store

Никаких сетевых запросов, никакого GUI.
"""
import json
import os
import sys
from pathlib import Path

from assistant.ui.settings_store import SettingsStore, UI_EDITABLE_KEYS


def _tmp_store(tmp_path: Path) -> SettingsStore:
    return SettingsStore(path=tmp_path / "settings.json")


def test_store_has_ui_editable_keys():
    assert "ASSISTANT_NAME" in UI_EDITABLE_KEYS
    assert "LLM_PROVIDER" in UI_EDITABLE_KEYS
    assert "TTS_PROVIDER" in UI_EDITABLE_KEYS
    assert "WHISPER_MODEL" in UI_EDITABLE_KEYS
    # mute НЕ должен быть здесь ни под каким именем.
    assert not any("mute" in k.lower() for k in UI_EDITABLE_KEYS)


def test_store_save_and_load(tmp_path):
    store = _tmp_store(tmp_path)
    store.save_from({"ASSISTANT_NAME": "Алеся"})
    assert store.has("ASSISTANT_NAME")
    assert store.get("ASSISTANT_NAME") == "Алеся"

    # Перезагрузка из того же файла.
    store2 = SettingsStore(path=tmp_path / "settings.json")
    assert store2.get("ASSISTANT_NAME") == "Алеся"


def test_store_rejects_unknown_key(tmp_path):
    store = _tmp_store(tmp_path)
    try:
        store.set("HACK_ME", 1)
        raise AssertionError("Ожидалось KeyError")
    except KeyError:
        pass


def test_store_filters_unknown_on_save(tmp_path):
    store = _tmp_store(tmp_path)
    store.save_from({
        "ASSISTANT_NAME": "Алеся",
        "UNKNOWN_KEY": "should_be_dropped",
    })
    raw = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    assert "UNKNOWN_KEY" not in raw
    assert raw.get("ASSISTANT_NAME") == "Алеся"


def test_store_drops_empty_values_on_save(tmp_path):
    store = _tmp_store(tmp_path)
    store.save_from({
        "ASSISTANT_NAME": "Алеся",
        "LLM_PROVIDER": "",
        "TTS_PROVIDER": None,
    })
    raw = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    assert raw.get("ASSISTANT_NAME") == "Алеся"
    assert "LLM_PROVIDER" not in raw
    assert "TTS_PROVIDER" not in raw


def test_store_apply_to_config_updates_config(tmp_path):
    from config import Config
    store = _tmp_store(tmp_path)
    store.save_from({"ASSISTANT_NAME": "ТестовоеИмя"})
    assert Config.ASSISTANT_NAME == "ТестовоеИмя"


def test_store_publishes_config_changed_event(tmp_path):
    from assistant.events import EventBus, EventType
    bus = EventBus()
    seen = []
    bus.subscribe(EventType.CONFIG_CHANGED, lambda e: seen.append(e))

    store = SettingsStore(path=tmp_path / "settings.json", bus=bus)
    store.save_from({"ASSISTANT_NAME": "Икс"})

    assert seen, "CONFIG_CHANGED не опубликовано"
    keys = seen[0].payload.get("changed_keys") or []
    assert "ASSISTANT_NAME" in keys


def test_store_alias_list_coercion(tmp_path):
    from config import Config
    store = _tmp_store(tmp_path)
    store.save_from({"ASSISTANT_ALIASES": "Алеся, Помощник"})
    assert Config.ASSISTANT_ALIASES == ["алеся", "помощник"]


def run_all():
    tests = [
        test_store_has_ui_editable_keys,
        test_store_rejects_unknown_key,
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
    print()
    print(f"=== {len(tests) - failed}/{len(tests)} SETTINGS TESTS PASSED (direct) ===", flush=True)
    return failed


def main():
    if not os.path.exists("assistant"):
        print("Запускать из корня проекта.", flush=True)
        sys.exit(2)
    sys.exit(1 if run_all() else 0)


if __name__ == "__main__":
    main()
