"""
Тесты config.Config — фактический контракт.

Запуск через pytest:
    pytest -v tools/test_config.py
Прямой запуск:
    python -m tools.test_config

Тесты НЕ печатают содержимое API-ключей.
Значения env, которые мы устанавливаем, — фиктивные строки
(или пустые строки там, где проверяем defaults).
"""
import importlib
import os
import sys


def _reload_config():
    """
    Перезагружает config.py, чтобы он перечитал os.environ.
    Возвращает модуль.
    """
    import config as config_module
    importlib.reload(config_module)
    return config_module


# ---------------------------------------------------------------------------
# LLM provider / keys
# ---------------------------------------------------------------------------

def test_llm_provider_default(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    cfg = _reload_config()
    assert cfg.Config.LLM_PROVIDER == "router"


def test_llm_provider_from_env_lowercase(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "ROUTER")
    cfg = _reload_config()
    assert cfg.Config.LLM_PROVIDER == "router"


def test_gemini_api_key_from_env(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-gemini-key-12345")
    cfg = _reload_config()
    assert cfg.Config.GEMINI_API_KEY == "fake-gemini-key-12345"


def test_openrouter_api_key_from_env(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake-openrouter-key-12345")
    cfg = _reload_config()
    assert cfg.Config.OPENROUTER_API_KEY == "fake-openrouter-key-12345"


def test_deepseek_api_key_from_env(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fake-deepseek-key-12345")
    cfg = _reload_config()
    assert cfg.Config.DEEPSEEK_API_KEY == "fake-deepseek-key-12345"


def test_keys_default_empty(monkeypatch):
    """
    Проверка отсутствия ключей.

    Мы НЕ полагаемся на delenv: load_dotenv() при override=False
    не перезаписывает уже существующие env-переменные, поэтому пустая
    строка, установленная через monkeypatch.setenv, переживёт load_dotenv().
    В assertion не выводим содержимое ключа — только факт равенства "".
    """
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "")

    cfg = _reload_config()
    assert cfg.Config.GEMINI_API_KEY == ""
    assert cfg.Config.OPENROUTER_API_KEY == ""
    assert cfg.Config.DEEPSEEK_API_KEY == ""


# ---------------------------------------------------------------------------
# Defaults для ключевых параметров
# ---------------------------------------------------------------------------

def test_defaults_for_core_params(monkeypatch):
    for k in (
        "GEMINI_MODEL", "OPENROUTER_MODEL", "OPENROUTER_BASE_URL",
        "WHISPER_MODEL", "WHISPER_LANGUAGE",
        "TTS_PROVIDER", "TTS_VOICE_HINT", "SILERO_SPEAKER",
        "ASSISTANT_NAME",
    ):
        monkeypatch.delenv(k, raising=False)
    cfg = _reload_config()
    C = cfg.Config

    assert C.GEMINI_MODEL == "gemini-3.1-flash-lite"
    assert C.OPENROUTER_MODEL == "openrouter/free"
    assert C.OPENROUTER_BASE_URL == "https://openrouter.ai/api/v1"
    assert C.WHISPER_MODEL == "small"
    assert C.WHISPER_LANGUAGE == "ru"
    assert C.TTS_PROVIDER == "silero"
    assert C.TTS_VOICE_HINT == "irina"
    assert C.SILERO_SPEAKER == "xenia"
    assert C.ASSISTANT_NAME == "Ассистент"


# ---------------------------------------------------------------------------
# ASSISTANT_ALIASES
# ---------------------------------------------------------------------------

def test_assistant_aliases_from_env(monkeypatch):
    monkeypatch.setenv("ASSISTANT_ALIASES", "Ассистент,Алекс,EVA")
    cfg = _reload_config()
    aliases = cfg.Config.ASSISTANT_ALIASES
    assert isinstance(aliases, list)
    assert aliases == ["ассистент", "алекс", "eva"]


def test_assistant_aliases_ignores_empty_items(monkeypatch):
    monkeypatch.setenv("ASSISTANT_ALIASES", "Ассистент, , Алекс,,")
    cfg = _reload_config()
    aliases = cfg.Config.ASSISTANT_ALIASES
    assert aliases == ["ассистент", "алекс"]


# ---------------------------------------------------------------------------
# AVATAR_MAP
# ---------------------------------------------------------------------------

def test_avatar_map_default_keys(monkeypatch):
    monkeypatch.delenv("AVATAR_MAP_JSON", raising=False)
    cfg = _reload_config()
    amap = cfg.Config.AVATAR_MAP
    for key in ("idle", "listening", "thinking", "speaking",
                "waiting_confirmation", "error"):
        assert key in amap, key
        assert isinstance(amap[key], str)
        assert amap[key]


def test_avatar_map_json_override(monkeypatch):
    monkeypatch.setenv(
        "AVATAR_MAP_JSON",
        '{"idle":"idle.gif","speaking":"talk.gif","custom":"x.png"}',
    )
    cfg = _reload_config()
    amap = cfg.Config.AVATAR_MAP

    assert amap["idle"] == "idle.gif"
    assert amap["speaking"] == "talk.gif"
    assert amap["custom"] == "x.png"
    assert amap["listening"]
    assert amap["thinking"]
    assert amap["waiting_confirmation"]
    assert amap["error"]


def test_avatar_map_json_invalid_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("AVATAR_MAP_JSON", "{not valid json")
    cfg = _reload_config()
    amap = cfg.Config.AVATAR_MAP
    assert amap["idle"]
    assert amap["speaking"]


# ---------------------------------------------------------------------------
# Пути, посчитанные через paths
# ---------------------------------------------------------------------------

def test_paths_are_strings(monkeypatch):
    for k in ("SILERO_MODEL_PATH", "AVATAR_DIR", "GRADEBOOK_PATH"):
        monkeypatch.delenv(k, raising=False)
    cfg = _reload_config()
    assert isinstance(cfg.Config.SILERO_MODEL_PATH, str)
    assert isinstance(cfg.Config.AVATAR_DIR, str)
    assert isinstance(cfg.Config.GRADEBOOK_PATH, str)
    assert cfg.Config.SILERO_MODEL_PATH
    assert cfg.Config.AVATAR_DIR
    assert cfg.Config.GRADEBOOK_PATH


# ---------------------------------------------------------------------------
# Прямой запуск
# ---------------------------------------------------------------------------

class _NoMonkeypatch:
    """Минимальная заглушка monkeypatch для прямого запуска."""
    def setenv(self, k, v):
        os.environ[k] = v

    def delenv(self, k, raising=True):
        if k in os.environ:
            del os.environ[k]


def _run_all():
    tests = [
        lambda: test_paths_are_strings(_NoMonkeypatch()),
        lambda: test_avatar_map_default_keys(_NoMonkeypatch()),
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print("[OK]", flush=True)
        except AssertionError as e:
            failed += 1
            print(f"[FAIL] {e}", flush=True)
        except Exception as e:
            failed += 1
            print(f"[ERROR] {type(e).__name__}: {e}", flush=True)
    print(flush=True)
    print(f"=== {len(tests) - failed}/{len(tests)} CONFIG TESTS PASSED (direct) ===", flush=True)
    return failed


def main():
    if not os.path.exists("assistant"):
        print("Запускать из корня проекта.", flush=True)
        sys.exit(2)
    sys.exit(1 if _run_all() else 0)


if __name__ == "__main__":
    main()
