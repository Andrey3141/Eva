def test_assistant_name_runtime(tmp_path):
    from assistant.ui.settings_store import SettingsStore
    from assistant.wake.keyword_detector import KeywordWakeDetector
    from config import Config

    saved_name = Config.ASSISTANT_NAME
    saved_aliases = list(Config.ASSISTANT_ALIASES)
    try:
        store = SettingsStore(path=tmp_path / "settings.json")
        # Явно очищаем алиасы, чтобы проверить, что работает только имя.
        store.save_from({
            "ASSISTANT_NAME": "ПроверкаИмени",
            "ASSISTANT_ALIASES": "",
        })
        assert Config.ASSISTANT_NAME == "ПроверкаИмени"
        assert Config.ASSISTANT_ALIASES == []

        d = KeywordWakeDetector()
        assert d.detect("ПроверкаИмени, привет").is_addressed is True
        # Старые значения не должны реагировать.
        assert d.detect("Алеся, привет").is_addressed is False
        assert d.detect("Ассистент, привет").is_addressed is False
    finally:
        Config.ASSISTANT_NAME = saved_name
        Config.ASSISTANT_ALIASES = saved_aliases


def test_assistant_aliases_runtime(tmp_path):
    from assistant.ui.settings_store import SettingsStore
    from assistant.wake.keyword_detector import KeywordWakeDetector
    from config import Config

    saved_name = Config.ASSISTANT_NAME
    saved_aliases = list(Config.ASSISTANT_ALIASES)
    try:
        store = SettingsStore(path=tmp_path / "settings.json")
        store.save_from({
            "ASSISTANT_NAME": "Тест",
            "ASSISTANT_ALIASES": "тестик, testy",
        })
        assert "тестик" in Config.ASSISTANT_ALIASES

        d = KeywordWakeDetector()
        assert d.detect("Тестик, привет").is_addressed is True
        assert d.detect("testy, hello").is_addressed is True
        assert d.detect("Тест, привет").is_addressed is True
    finally:
        Config.ASSISTANT_NAME = saved_name
        Config.ASSISTANT_ALIASES = saved_aliases
