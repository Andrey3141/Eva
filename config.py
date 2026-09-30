import json
import os

from dotenv import load_dotenv

from assistant import paths

_env_file = paths.env_file_path()
if _env_file is not None:
    load_dotenv(dotenv_path=str(_env_file))
else:
    load_dotenv(dotenv_path=None, override=False)


_DEFAULT_AVATAR_MAP = {
    "idle": "idle.png",
    "listening": "listening.png",
    "thinking": "thinking.png",
    "speaking": "speaking_1.png",
    "waiting_confirmation": "confirmation.png",
    "error": "error.png",
}


class Config:
    # --- Логирование ---
    EVA_LOG_LEVEL = os.getenv("EVA_LOG_LEVEL", "DEBUG")
    EVA_LOG_DIR = os.getenv("EVA_LOG_DIR", "").strip() or None

    # --- LLM ---
    LLM_PROVIDER = os.getenv("LLM_PROVIDER", "echo").lower()

    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
    DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
    DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")

    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL = os.getenv("GROQ_MODEL", "")
    GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")

    CEREBRAS_API_KEY = os.getenv("CEREBRAS_API_KEY", "")
    CEREBRAS_MODEL = os.getenv("CEREBRAS_MODEL", "")
    CEREBRAS_BASE_URL = os.getenv("CEREBRAS_BASE_URL", "https://api.cerebras.ai/v1")

    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
    OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openrouter/free")
    OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

    LLM_ROUTER_COOLDOWN_SEC = float(os.getenv("LLM_ROUTER_COOLDOWN_SEC", "30"))

    # --- Ассистент ---
    ASSISTANT_NAME = os.getenv("ASSISTANT_NAME", "Алеся")
    ASSISTANT_ALIASES = [
        a.strip().lower()
        for a in os.getenv("ASSISTANT_ALIASES", "").split(",")
        if a.strip()
    ]

    # --- STT ---
    WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")
    WHISPER_LANGUAGE = os.getenv("WHISPER_LANGUAGE", "ru")

    # --- TTS ---
    TTS_PROVIDER = os.getenv("TTS_PROVIDER", "silero").lower()
    TTS_VOICE_HINT = os.getenv("TTS_VOICE_HINT", "irina")
    SILERO_SPEAKER = os.getenv("SILERO_SPEAKER", "xenia")

    SILERO_MODEL_PATH = str(paths.silero_model_path())
    AVATAR_DIR = str(paths.avatar_dir())
    GRADEBOOK_PATH = str(paths.gradebook_path())

    # --- Презентации / видео ---
    PRESENTATIONS_DIR = str(paths.presentations_dir())
    PRESENTATION_MATCH_THRESHOLD = float(
        os.getenv("PRESENTATION_MATCH_THRESHOLD", "0.70")
    )
    PRESENTATION_AMBIGUITY_MARGIN = float(
        os.getenv("PRESENTATION_AMBIGUITY_MARGIN", "0.05")
    )

    # --- Режим извлечения параметров ---
    PARAMETER_ROUTER_MODE = os.getenv("PARAMETER_ROUTER_MODE", "ml").lower()

    # --- Запись ---
    RECORD_SECONDS = float(os.getenv("RECORD_SECONDS", "5"))
    SAMPLE_RATE = int(os.getenv("SAMPLE_RATE", "16000"))

    # --- UI ---
    UI_ANIMATIONS_ENABLED = os.getenv("UI_ANIMATIONS_ENABLED", "true").lower() == "true"
    UI_VOLUME = float(os.getenv("UI_VOLUME", "1.0"))
    UI_SPEECH_RATE = int(os.getenv("UI_SPEECH_RATE", "180"))
    UI_DEBUG = os.getenv("UI_DEBUG", "false").lower() == "true"

    # --- UI-выбор аудиоустройства (persisted в settings.json) ---
    INPUT_DEVICE_INDEX = None

    # --- Confidence ---
    CONFIDENCE_EXECUTE = float(os.getenv("CONFIDENCE_EXECUTE", "0.95"))
    CONFIDENCE_CLARIFY = float(os.getenv("CONFIDENCE_CLARIFY", "0.70"))

    @staticmethod
    def _load_avatar_map() -> dict:
        raw = os.getenv("AVATAR_MAP_JSON", "").strip()
        if raw:
            try:
                user_map = json.loads(raw)
                if isinstance(user_map, dict):
                    merged = dict(_DEFAULT_AVATAR_MAP)
                    merged.update({str(k): str(v) for k, v in user_map.items()})
                    return merged
            except json.JSONDecodeError:
                pass
        return dict(_DEFAULT_AVATAR_MAP)

    AVATAR_MAP = _load_avatar_map.__func__()

    # ------------------------------------------------------------------
    # UI-editable keys
    # ------------------------------------------------------------------

    @classmethod
    def ui_editable_keys(cls) -> set[str]:
        return {
            "ASSISTANT_NAME",
            "ASSISTANT_ALIASES",
            "WHISPER_MODEL",
            "WHISPER_LANGUAGE",
            "TTS_PROVIDER",
            "SILERO_SPEAKER",
            "LLM_PROVIDER",
            "GEMINI_MODEL",
            "GROQ_MODEL",
            "CEREBRAS_MODEL",
            "OPENROUTER_MODEL",
            "DEEPSEEK_MODEL",
            "UI_ANIMATIONS_ENABLED",
            "UI_VOLUME",
            "UI_SPEECH_RATE",
            "INPUT_DEVICE_INDEX",
            "PRESENTATIONS_DIR",
            "GRADEBOOK_PATH",
            "PRESENTATION_MATCH_THRESHOLD",
            "PRESENTATION_AMBIGUITY_MARGIN",
            "PARAMETER_ROUTER_MODE",
        }

    @classmethod
    def apply_store(cls, store) -> None:
        allowed = cls.ui_editable_keys()
        for key in allowed:
            if key == "ASSISTANT_ALIASES":
                continue
            if not store.has(key):
                continue
            value = store.get(key)
            current = getattr(cls, key, None)
            coerced = _coerce_like(value, current)
            setattr(cls, key, coerced)

        if store.has("ASSISTANT_ALIASES"):
            raw = store.get("ASSISTANT_ALIASES")
            if isinstance(raw, str):
                parts = [a.strip().lower() for a in raw.split(",") if a.strip()]
            elif isinstance(raw, list):
                parts = [str(a).strip().lower() for a in raw if str(a).strip()]
            else:
                parts = []
            cls.ASSISTANT_ALIASES = parts


def _coerce_like(value, current):
    if current is None:
        return value
    try:
        if isinstance(current, bool):
            if isinstance(value, str):
                return value.strip().lower() in ("1", "true", "yes", "on")
            return bool(value)
        if isinstance(current, int) and not isinstance(current, bool):
            return int(value)
        if isinstance(current, float):
            return float(value)
        if isinstance(current, str):
            return str(value)
    except (TypeError, ValueError):
        return current
    return value
