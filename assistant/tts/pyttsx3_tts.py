import pyttsx3
from .base import TTSEngine
from config import Config


class Pyttsx3TTS(TTSEngine):
    def __init__(
        self,
        voice_hint: str | None = None,
        volume: float | None = None,
        rate: int | None = None,
    ):
        self.engine = pyttsx3.init()

        # Громкость и скорость речи — из Config, если не переданы явно.
        # Значения применяются через setProperty, поэтому фактически
        # используются при воспроизведении.
        vol = float(volume) if volume is not None else float(Config.UI_VOLUME)
        vol = max(0.0, min(1.0, vol))
        self.engine.setProperty("volume", vol)

        r = int(rate) if rate is not None else int(Config.UI_SPEECH_RATE)
        self.engine.setProperty("rate", r)

        hint = (voice_hint or Config.TTS_VOICE_HINT).lower()
        if hint:
            for v in self.engine.getProperty("voices"):
                if hint in (v.name or "").lower() or hint in (v.id or "").lower():
                    self.engine.setProperty("voice", v.id)
                    break

    def speak(self, text: str) -> None:
        if not text:
            return
        self.engine.say(text)
        self.engine.runAndWait()
