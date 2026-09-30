"""
Smoke-тесты реального FastEmbedProvider.

Проверяют:
  - модель загружается через установленный fastembed;
  - embed() возвращает L2-нормализованный вектор размерности 384;
  - семантическое сходство: близкие по смыслу фразы ближе, чем далёкие.

Пропускаются, если fastembed не установлен или модель недоступна.
"""
import math

import pytest

fastembed = pytest.importorskip("fastembed")

from assistant.intent.router.providers import FastEmbedProvider


def _cosine(a, b) -> float:
    return sum(x * y for x, y in zip(a, b))


def test_fastembed_provider_embeds_russian_query():
    provider = FastEmbedProvider()

    vectors = provider.embed(
        ["открой видео про трансформаторы"],
        role="query",
    )

    assert isinstance(vectors, list)
    assert len(vectors) == 1
    vec = vectors[0]
    assert isinstance(vec, list)
    assert len(vec) == 384, f"expected 384 dim, got {len(vec)}"

    norm = math.sqrt(sum(x * x for x in vec))
    assert abs(norm - 1.0) < 1e-3, f"norm={norm}"


def test_fastembed_provider_passage_vs_query_same_dim():
    provider = FastEmbedProvider()
    q = provider.embed(["трансформаторы"], role="query")[0]
    p = provider.embed(["трансформаторы"], role="passage")[0]
    assert len(q) == len(p) == 384


def test_semantic_similarity_relative():
    """
    Относительная проверка: одна тема ближе, чем другая.

    Не задаём абсолютный threshold вроде 0.8, чтобы не привязываться
    к конкретной модели. Достаточно, что близкие по смыслу фразы
    дают больший cosine, чем семантически далёкие.
    """
    provider = FastEmbedProvider()

    vectors = provider.embed(
        [
            "открой видео про трансформаторы",
            "покажи ролик о трансформаторах",
            "поставь Сидорову пять",
        ],
        role="passage",
    )

    assert len(vectors) == 3

    similar = _cosine(vectors[0], vectors[1])
    different = _cosine(vectors[0], vectors[2])

    assert similar > different, (
        f"similar={similar:.3f} должно быть больше different={different:.3f}"
    )


def test_semantic_similarity_intents():
    """
    Дополнительно: фразы про один intent должны быть ближе,
    чем про разные intent.
    """
    provider = FastEmbedProvider()

    vectors = provider.embed(
        [
            "включи видео",
            "запусти ролик",
            "открой презентацию",
        ],
        role="passage",
    )

    video_vs_video = _cosine(vectors[0], vectors[1])
    video_vs_pres = _cosine(vectors[0], vectors[2])

    assert video_vs_video > video_vs_pres, (
        f"video↔video={video_vs_video:.3f} "
        f"должно быть больше video↔presentation={video_vs_pres:.3f}"
    )
