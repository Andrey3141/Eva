"""
Embedding-провайдеры.

EmbeddingProvider — ABC: embed(texts) -> list[list[float]].

Реализации:
  - FastEmbedProvider — sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
    через fastembed (ONNX, CPU). Модель multilingual, 384 dim.
  - HashingEmbeddingProvider — детерминированный fallback для тестов
    и явного офлайн-режима. НЕ semantic.

Кэш модели: постоянный каталог paths.fastembed_cache_dir(),
переживает перезапуски Python/pytest. Переопределяется
env EVA_FASTEMBED_CACHE_DIR.
"""
from __future__ import annotations

import hashlib
import os
from abc import ABC, abstractmethod
from typing import Iterable, Optional

import numpy as np

from assistant import paths


class EmbeddingProvider(ABC):
    """Абстрактный провайдер эмбеддингов."""

    @abstractmethod
    def embed(self, texts: Iterable[str], role: str = "passage") -> list[list[float]]:
        """Возвращает L2-нормализованные вектора."""

    @property
    def dimension(self) -> int:
        raise NotImplementedError


class FastEmbedProvider(EmbeddingProvider):
    """
    Embeddings через fastembed (ONNX, CPU).

    Модель: sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
      - multilingual (~50 языков, включая русский);
      - dimension 384;
      - ~0.22 GB ONNX;
      - БЕЗ обязательных префиксов query:/passage:.

    Кэш:
      - по умолчанию <user_cache_dir>/fastembed;
      - переопределяется через cache_dir или EVA_FASTEMBED_CACHE_DIR;
      - создаётся автоматически;
      - переживает перезапуски Python/pytest.
    """

    DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        cache_dir: Optional[str] = None,
    ):
        self.model_name = model_name
        if cache_dir:
            self._cache_dir = str(cache_dir)
        else:
            self._cache_dir = str(paths.fastembed_cache_dir())
        self._model = None
        self._dim: Optional[int] = None

    @property
    def cache_dir(self) -> str:
        return self._cache_dir

    def _ensure_model(self):
        if self._model is not None:
            return self._model
        try:
            from fastembed import TextEmbedding
        except Exception as e:
            raise RuntimeError(f"fastembed недоступен: {e}") from e

        # Явный cache_dir: модель скачается один раз и будет
        # переиспользоваться между запусками.
        self._model = TextEmbedding(
            model_name=self.model_name,
            cache_dir=self._cache_dir,
        )
        return self._model

    def embed(self, texts: Iterable[str], role: str = "passage") -> list[list[float]]:
        items = list(texts)
        if not items:
            return []

        model = self._ensure_model()

        # Модель не требует префиксов query:/passage:.
        vectors = list(model.embed(items))

        out: list[list[float]] = []
        for v in vectors:
            arr = np.asarray(v, dtype="float32")
            norm = float(np.linalg.norm(arr))
            if norm > 0:
                arr = arr / norm
            out.append(arr.tolist())

        if self._dim is None and out:
            self._dim = len(out[0])
        return out

    @property
    def dimension(self) -> int:
        if self._dim is None:
            self.embed(["_"], role="query")
        return int(self._dim or 0)


class HashingEmbeddingProvider(EmbeddingProvider):
    """Детерминированный fallback для тестов. НЕ semantic."""

    def __init__(self, dim: int = 256):
        self._dim = int(dim)

    def embed(self, texts: Iterable[str], role: str = "passage") -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            vec = np.zeros(self._dim, dtype="float32")
            low = (text or "").lower().strip()
            padded = f"_{low}_"
            for n in (2, 3, 4):
                for i in range(len(padded) - n + 1):
                    gram = padded[i:i + n]
                    h = hashlib.md5(gram.encode("utf-8")).digest()
                    idx = int.from_bytes(h[:4], "little") % self._dim
                    sign = 1.0 if (h[4] & 1) else -1.0
                    vec[idx] += sign
            norm = float(np.linalg.norm(vec))
            if norm > 0:
                vec = vec / norm
            out.append(vec.tolist())
        return out

    @property
    def dimension(self) -> int:
        return self._dim


# ---------------------------------------------------------------------------
# Глобальный кэш провайдера
# ---------------------------------------------------------------------------

_DEFAULT_PROVIDER: Optional[EmbeddingProvider] = None


def get_default_embedding_provider() -> EmbeddingProvider:
    """
    Возвращает разделяемый EmbeddingProvider.

    Production: FastEmbedProvider с постоянным cache_dir
    (paths.fastembed_cache_dir()), с warmup при первом вызове.

    Если fastembed не установлен или модель не поддерживается —
    поднимается исключение. Молчаливого отката на hashing НЕТ.

    Явный opt-in для hashing: env EVA_EMBEDDING_PROVIDER=hashing.
    """
    global _DEFAULT_PROVIDER
    if _DEFAULT_PROVIDER is not None:
        return _DEFAULT_PROVIDER

    mode = os.getenv("EVA_EMBEDDING_PROVIDER", "").strip().lower()

    if mode == "hashing":
        _DEFAULT_PROVIDER = HashingEmbeddingProvider()
        return _DEFAULT_PROVIDER

    provider = FastEmbedProvider()
    # Warmup: загружаем модель сейчас. Если модель не поддерживается —
    # ошибка выявится при старте EVA, а не в worker-потоке.
    provider.embed(["проверка русского текста"], role="query")
    _DEFAULT_PROVIDER = provider
    return _DEFAULT_PROVIDER


def set_default_embedding_provider(provider: EmbeddingProvider) -> None:
    global _DEFAULT_PROVIDER
    _DEFAULT_PROVIDER = provider


def reset_default_provider() -> None:
    global _DEFAULT_PROVIDER
    _DEFAULT_PROVIDER = None
