"""
Минимальный тест Gemini-провайдера через существующий интерфейс EVA.
Не задействует микрофон, STT и UI.

Запуск:
    python -m tools.test_gemini_provider
"""
import sys

from assistant.llm.gemini_provider import GeminiLLM
from config import Config


def main() -> int:
    print("=== GEMINI PROVIDER TEST ===", flush=True)
    print(f"LLM_PROVIDER = {Config.LLM_PROVIDER}", flush=True)
    print(f"GEMINI_MODEL = {Config.GEMINI_MODEL}", flush=True)

    llm = GeminiLLM()

    # Тест 1. Обычный вопрос.
    q1 = "Сколько будет 25 умножить на 4?"
    print("", flush=True)
    print(f"[USER] {q1}", flush=True)
    a1 = llm.chat(q1, "Отвечай кратко по-русски.")
    print(f"[GEMINI] {a1}", flush=True)

    # Тест 2. Команда EVA — структурированный ответ.
    # Через LLMIntentParser, чтобы проверить интерфейсный путь.
    q2 = "Сидоров 2 балла"
    print("", flush=True)
    print(f"[USER] {q2}", flush=True)
    from assistant.intent.llm_intent_parser import SYSTEM_PROMPT as INTENT_SYSTEM
    a2 = llm.chat(q2, INTENT_SYSTEM)
    print(f"[GEMINI] {a2}", flush=True)

    print("", flush=True)
    print("=== DONE ===", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
