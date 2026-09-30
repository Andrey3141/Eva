from abc import ABC, abstractmethod
import numpy as np


class STTEngine(ABC):
    @abstractmethod
    def transcribe(self, audio: np.ndarray, sample_rate: int) -> str:
        ...
