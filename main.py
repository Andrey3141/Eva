import os
from datetime import datetime

# 1. Самое первое, что делает EVA — настраивает логирование.
from assistant.logging_setup import setup_logging, install_exception_hooks, get_logger, log_config_summary

_log_file = setup_logging(to_console=False)
install_exception_hooks()
log = get_logger("main")

# 2. Применяем пользовательские настройки (settings.json) ДО создания
#    любых провайдеров/парсеров, чтобы Config уже содержал актуальные значения.
from assistant.ui.settings_store import SettingsStore
_settings_store = SettingsStore()
_settings_store.apply_to_config()

from config import Config
log_config_summary(Config)

from assistant.events import EventBus
from assistant import paths

from assistant.stt.whisper_stt import WhisperSTT
from assistant.wake.keyword_detector import KeywordWakeDetector

from assistant.llm.deepseek_llm import DeepSeekLLM
from assistant.llm.echo_llm import EchoLLM
from assistant.llm.gemini_provider import GeminiLLM
from assistant.llm.groq_provider import GroqLLM
from assistant.llm.cerebras_provider import CerebrasLLM
from assistant.llm.openrouter_provider import OpenRouterLLM
from assistant.llm.router import LLMRouter, LLMProviderConfig, NetworkChecker

from assistant.intent.llm_intent_parser import LLMIntentParser
from assistant.intent.echo_intent_parser import EchoIntentParser

from assistant.response.llm_response import LLMResponseGenerator
from assistant.response.echo_response import EchoResponseGenerator

from assistant.actions.base import ActionRegistry, ActionContext
from assistant.actions.actions_impl import (
    GradeStudentAction,
    OpenPresentationAction,
    OpenVideoAction,
    OpenExcelAction,
    ClosePresentationAction,
    CloseVideoAction,
    CloseExcelAction,
    CloseFileAction,
    RestartPresentationAction,
    RestartExcelAction,
    NextSlideAction,
)
from assistant.actions.validators import (
    GradeStudentValidator,
    OpenPresentationValidator,
    OpenVideoValidator,
    CloseActionValidator,
    RestartActionValidator,
    NextSlideValidator,
)

from assistant.gradebook import ExcelGradebook
from assistant.confirmation import KeywordConfirmationParser

from assistant.tts.pyttsx3_tts import Pyttsx3TTS
from assistant.tts.edge_tts import EdgeTTS
from assistant.tts.silero_tts import SileroTTS
from assistant.tts.fallback_tts import FallbackTTS

from assistant.audio import list_input_devices, pick_input_device, describe_device


# ---------------------------------------------------------------
# Дата занятия
# ---------------------------------------------------------------

def _today_dd_mm() -> str:
    now = datetime.now()
    return f"{now.day:02d}.{now.month:02d}"


# ---------------------------------------------------------------
# LLM
# ---------------------------------------------------------------

def _make_gemini_entry():
    if not Config.GEMINI_API_KEY:
        return None
    from assistant.llm.router.router import _Entry
    return _Entry(
        provider=GeminiLLM(),
        config=LLMProviderConfig(
            name="gemini", model=Config.GEMINI_MODEL, priority=1,
            requires_internet=True, supports_intent=True,
            supports_response=True, supports_json=True,
            timeout=10.0, max_retries=1,
        ),
    )


def _make_groq_entry():
    if not Config.GROQ_API_KEY or not Config.GROQ_MODEL:
        return None
    from assistant.llm.router.router import _Entry
    return _Entry(
        provider=GroqLLM(),
        config=LLMProviderConfig(
            name="groq", model=Config.GROQ_MODEL, priority=2,
            requires_internet=True, supports_intent=True,
            supports_response=True, supports_json=True,
            timeout=15.0, max_retries=1,
        ),
    )


def _make_cerebras_entry():
    if not Config.CEREBRAS_API_KEY or not Config.CEREBRAS_MODEL:
        return None
    from assistant.llm.router.router import _Entry
    return _Entry(
        provider=CerebrasLLM(),
        config=LLMProviderConfig(
            name="cerebras", model=Config.CEREBRAS_MODEL, priority=3,
            requires_internet=True, supports_intent=True,
            supports_response=True, supports_json=True,
            timeout=15.0, max_retries=1,
        ),
    )


def _make_openrouter_entry():
    if not Config.OPENROUTER_API_KEY:
        return None
    from assistant.llm.router.router import _Entry
    return _Entry(
        provider=OpenRouterLLM(),
        config=LLMProviderConfig(
            name="openrouter", model=Config.OPENROUTER_MODEL, priority=4,
            requires_internet=True, supports_intent=True,
            supports_response=True, supports_json=True,
            timeout=15.0, max_retries=1,
        ),
    )


def build_llm():
    provider = Config.LLM_PROVIDER

    if provider == "router":
        entries = []
        for factory in (_make_gemini_entry, _make_groq_entry,
                        _make_cerebras_entry, _make_openrouter_entry):
            e = factory()
            if e is not None:
                entries.append(e)

        if not entries:
            log.warning("[LLM Router] ни один провайдер не настроен, откат на echo.")
            return EchoLLM()

        names = ", ".join(e.config.name for e in entries)
        log.info("[LLM Router] провайдеры: %s", names)
        return LLMRouter(entries, network_checker=NetworkChecker(),
                         cooldown_seconds=Config.LLM_ROUTER_COOLDOWN_SEC)

    if provider == "gemini":
        if not Config.GEMINI_API_KEY:
            log.warning("[LLM] gemini: ключ не задан, откат на echo.")
            return EchoLLM()
        log.info("[LLM] Gemini / %s", Config.GEMINI_MODEL)
        return GeminiLLM()

    if provider == "groq":
        if not Config.GROQ_API_KEY or not Config.GROQ_MODEL:
            log.warning("[LLM] groq: ключ или модель не заданы, откат на echo.")
            return EchoLLM()
        log.info("[LLM] Groq / %s", Config.GROQ_MODEL)
        return GroqLLM()

    if provider == "cerebras":
        if not Config.CEREBRAS_API_KEY or not Config.CEREBRAS_MODEL:
            log.warning("[LLM] cerebras: ключ или модель не заданы, откат на echo.")
            return EchoLLM()
        log.info("[LLM] Cerebras / %s", Config.CEREBRAS_MODEL)
        return CerebrasLLM()

    if provider == "openrouter":
        if not Config.OPENROUTER_API_KEY:
            log.warning("[LLM] openrouter: ключ не задан, откат на echo.")
            return EchoLLM()
        log.info("[LLM] OpenRouter / %s", Config.OPENROUTER_MODEL)
        return OpenRouterLLM()

    if provider == "deepseek":
        if not Config.DEEPSEEK_API_KEY:
            log.warning("[LLM] deepseek: ключ не задан, откат на echo.")
            return EchoLLM()
        log.info("[LLM] DeepSeek / %s", Config.DEEPSEEK_MODEL)
        return DeepSeekLLM()

    log.info("[LLM] echo (без API)")
    return EchoLLM()


def _api_provider_configured() -> bool:
    provider = Config.LLM_PROVIDER
    if provider == "deepseek":
        return bool(Config.DEEPSEEK_API_KEY)
    if provider == "gemini":
        return bool(Config.GEMINI_API_KEY)
    if provider == "groq":
        return bool(Config.GROQ_API_KEY and Config.GROQ_MODEL)
    if provider == "cerebras":
        return bool(Config.CEREBRAS_API_KEY and Config.CEREBRAS_MODEL)
    if provider == "openrouter":
        return bool(Config.OPENROUTER_API_KEY)
    if provider == "router":
        return any((
            Config.GEMINI_API_KEY,
            Config.GROQ_API_KEY and Config.GROQ_MODEL,
            Config.CEREBRAS_API_KEY and Config.CEREBRAS_MODEL,
            Config.OPENROUTER_API_KEY,
        ))
    return False


def build_parameter_router(embedding_provider):
    from assistant.intent.parameter import (
        MLSlotTagger, EmbeddingCandidateScorer, ParameterFusion, ParameterRouter,
        load_parameter_examples,
    )
    from assistant.intent.parameter.facade import ParameterRouterFacade
    from кастыли import КастылиParameterRouter

    kastyli = КастылиParameterRouter()

    param_examples = load_parameter_examples()
    print(f"[BUILD_PARAMETER_ROUTER] parameter dataset examples="
          f"{len(param_examples)}", flush=True)

    if not param_examples:
        print("[BUILD_PARAMETER_ROUTER] ml unavailable, only кастыли",
              flush=True)
        return ParameterRouterFacade(ml_router=None, kastyli_router=kastyli)

    ml_tagger = MLSlotTagger(param_examples, min_confidence=0.30)
    emb_scorer = EmbeddingCandidateScorer(
        provider=embedding_provider,
        max_span_tokens=5,
        top_k=5,
    )
    fusion = ParameterFusion(min_ml=0.40, min_emb=0.45, agree_bonus=0.10)
    ml_router = ParameterRouter(ml_tagger, emb_scorer, fusion)

    print("[BUILD_PARAMETER_ROUTER] facade=ml+кастыли", flush=True)
    return ParameterRouterFacade(ml_router=ml_router, kastyli_router=kastyli)


def build_intent_router(llm):
    from assistant.intent.router import (
        EmbeddingRouter, MLIntentClassifier, IntentFusion,
        LLMIntentRouter, IntentRouter,
        load_intent_examples, get_default_embedding_provider,
    )

    examples = load_intent_examples()
    print(f"[BUILD_INTENT_ROUTER] dataset intents={len(examples)} "
          f"names={sorted(examples.keys())}", flush=True)
    if not examples:
        log.warning("[IntentRouter] датасет intent_examples.json пуст или не найден.")
        return None

    embedding_provider = get_default_embedding_provider()
    print(f"[BUILD_INTENT_ROUTER] embedding provider="
          f"{type(embedding_provider).__name__} "
          f"model={getattr(embedding_provider, 'model_name', '?')} "
          f"dim={getattr(embedding_provider, 'dimension', '?')}",
          flush=True)

    parameter_router = build_parameter_router(embedding_provider)
    if parameter_router is not None:
        print("[BUILD_INTENT_ROUTER] parameter_router=ParameterRouterFacade",
              flush=True)
    else:
        print("[BUILD_INTENT_ROUTER] parameter_router=ParameterExtractor "
              "(fallback)", flush=True)

    router = IntentRouter(
        embedding_router=EmbeddingRouter(
            examples=examples,
            provider=embedding_provider,
            min_score=0.5,
        ),
        ml_classifier=MLIntentClassifier(
            examples=examples,
            min_confidence=0.4,
        ),
        fusion=IntentFusion(
            min_individual=0.55,
            agree_bonus=0.05,
        ),
        llm_router=LLMIntentRouter(llm),
        confidence_threshold=0.75,
        parameter_router=parameter_router,
    )
    return router


def build_parsers(llm):
    provider = Config.LLM_PROVIDER
    print(f"[BUILD_PARSERS] LLM_PROVIDER={provider!r}", flush=True)

    if provider == "echo":
        print("[BUILD_PARSERS] intent_parser=EchoIntentParser (echo-режим)",
              flush=True)
        return EchoIntentParser(), EchoResponseGenerator()

    if not _api_provider_configured():
        print("[BUILD_PARSERS] intent_parser=EchoIntentParser "
              "(API-провайдер не настроен)", flush=True)
        return EchoIntentParser(), EchoResponseGenerator()

    intent_router = build_intent_router(llm)
    if intent_router is not None:
        print("[BUILD_PARSERS] intent_parser=IntentRouter", flush=True)
        return intent_router, LLMResponseGenerator(llm)

    print("[BUILD_PARSERS] intent_parser=LLMIntentParser "
          "(каскад не собрался, fallback)", flush=True)
    return LLMIntentParser(llm), LLMResponseGenerator(llm)


# ---------------------------------------------------------------
# TTS
# ---------------------------------------------------------------

def build_tts():
    provider = Config.TTS_PROVIDER

    if provider == "silero":
        log.info("[TTS] silero (offline)")
        return SileroTTS()

    if provider == "edge":
        log.info("[TTS] edge-tts (онлайн) + fallback Silero")
        return FallbackTTS(primary=EdgeTTS(), fallback=SileroTTS())

    log.info("[TTS] pyttsx3 (офлайн)")
    return Pyttsx3TTS()


# ---------------------------------------------------------------

def build_actions() -> ActionRegistry:
    reg = ActionRegistry()
    reg.register(GradeStudentAction(), GradeStudentValidator())
    reg.register(OpenPresentationAction(), OpenPresentationValidator())
    reg.register(OpenVideoAction(), OpenVideoValidator())
    reg.register(OpenExcelAction(), OpenPresentationValidator())
    reg.register(ClosePresentationAction(), CloseActionValidator())
    reg.register(CloseVideoAction(), CloseActionValidator())
    reg.register(CloseExcelAction(), CloseActionValidator())
    reg.register(CloseFileAction(), CloseActionValidator())
    reg.register(RestartPresentationAction(), RestartActionValidator())
    reg.register(RestartExcelAction(), RestartActionValidator())
    reg.register(NextSlideAction(), NextSlideValidator())
    return reg


def build_gradebook():
    pres_dir = Config.PRESENTATIONS_DIR
    print(f"[PRESENTATIONS] path={pres_dir}", flush=True)

    path = Config.GRADEBOOK_PATH
    abs_path = os.path.abspath(path)
    print(f"[GRADEBOOK] path={abs_path}", flush=True)

    if not os.path.exists(path):
        log.warning("[Gradebook] Файл не найден: %s", path)
        print(f"[GRADEBOOK] not found", flush=True)
        return None, path
    try:
        gb = ExcelGradebook()
        gb.load(path)
        print(f"[GRADEBOOK] sheet={gb.sheet_name} "
              f"students={len(gb.get_students())}", flush=True)
        log.info("[Gradebook] %s, лист %s, учеников %d",
                 path, gb.sheet_name, len(gb.get_students()))
        return gb, path
    except Exception as e:
        log.exception("[Gradebook] Ошибка загрузки %s: %s", path, e)
        print(f"[GRADEBOOK] load error: {e}", flush=True)
        return None, path


def build_context() -> ActionContext:
    gb, path = build_gradebook()
    today = _today_dd_mm()
    print(f"[GRADEBOOK] current_lesson={today}", flush=True)
    return ActionContext(
        addressed_to_assistant=False,
        current_subject="Электроснабжение",
        current_lesson=today,
        gradebook=gb,
        gradebook_path=path,
        known_students=gb.get_students() if gb else [],
        dry_run=False,
        presentations_dir=Config.PRESENTATIONS_DIR,
        presentation_match_threshold=float(Config.PRESENTATION_MATCH_THRESHOLD),
        presentation_ambiguity_margin=float(Config.PRESENTATION_AMBIGUITY_MARGIN),
    )


def print_audio_diagnostics() -> None:
    log.info("[AUDIO] Сканирую устройства ввода…")
    devices = list_input_devices()
    if not devices:
        log.warning("[AUDIO] Устройства ввода не найдены.")
        return

    for d in devices:
        mark = " (default)" if d.is_default else ""
        mon = " [monitor]" if d.is_monitor else ""
        log.info("[AUDIO]   #%d %r · %s · ch=%d · sr=%.0f%s%s",
                 d.index, d.name, d.hostapi, d.channels,
                 d.default_samplerate, mark, mon)

    chosen = pick_input_device()
    if chosen is None:
        log.warning("[AUDIO] Не найдено физического микрофона.")
    else:
        log.info("[AUDIO] Выбран: %s", describe_device(chosen))


# ---------------------------------------------------------------

def main():
    log.info(paths.describe().replace("\n", " | "))

    bus = EventBus()
    print_audio_diagnostics()

    llm = build_llm()
    intent_parser, response_gen = build_parsers(llm)

    core = __import__("assistant.core", fromlist=["AssistantCore"]).AssistantCore(
        stt=WhisperSTT(),
        wake=KeywordWakeDetector(),
        intent_parser=intent_parser,
        response_gen=response_gen,
        actions=build_actions(),
        tts=build_tts(),
        confirmation_parser=KeywordConfirmationParser(),
        context=build_context(),
    )

    from assistant.ui.app import run_app
    log.info("EVA запускает UI")
    run_app(
        core, bus,
        settings_store=_settings_store,
        rebuild_callbacks={
            "llm": build_llm,
            "parsers": build_parsers,
            "stt": lambda: WhisperSTT(),
            "tts": build_tts,
        },
    )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log.exception("Fatal error in main()")
        raise
