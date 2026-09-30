from .base import TTSEngine


class FallbackTTS(TTSEngine):
    """
    Последовательно пробует primary, при ошибке — fallback.
    После первой ошибки primary помечается недоступным
    и больше не вызывается до перезапуска приложения.

    Использование:
        FallbackTTS(primary=EdgeTTS(), fallback=SileroTTS())

    Логи:
        [TTS] EdgeTTS недоступен, переход на локальный Silero TTS (...)
        [TTS] ERROR: EdgeTTS и Silero TTS недоступны
    """

    def __init__(self, primary: TTSEngine, fallback: TTSEngine):
        self._primary = primary
        self._fallback = fallback
        self._primary_available = True

    @property
    def primary_available(self) -> bool:
        return self._primary_available

    def speak(self, text: str) -> None:
        if not text:
            return

        # 1) Пробуем primary, пока он считается доступным.
        if self._primary_available:
            try:
                self._primary.speak(text)
                return
            except Exception as e:
                print(
                    f"[TTS] EdgeTTS недоступен, переход на локальный Silero TTS "
                    f"({type(e).__name__}: {e})",
                    flush=True,
                )
                self._primary_available = False

        # 2) Fallback.
        try:
            self._fallback.speak(text)
            return
        except Exception as e:
            print(
                f"[TTS] ERROR: EdgeTTS и Silero TTS недоступны "
                f"({type(e).__name__}: {e})",
                flush=True,
            )
            raise

    def stop(self) -> None:
        for engine in (self._primary, self._fallback):
            try:
                engine.stop()
            except Exception:
                pass
