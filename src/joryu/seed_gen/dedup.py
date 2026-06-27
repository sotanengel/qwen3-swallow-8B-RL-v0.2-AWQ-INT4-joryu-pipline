"""Stage2 意味類似重複排除 (cosine similarity)。"""

from __future__ import annotations

import hashlib
import logging
import math
from typing import Protocol

logger = logging.getLogger(__name__)


class EmbeddingBackend(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class FakeEmbeddingBackend:
    """決定的な低次元ベクトル (CI / --fake-llm 用)。"""

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            vec = [float(b) / 255.0 for b in digest[:16]]
            out.append(vec)
        return out


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na <= 0 or nb <= 0:
        return 0.0
    return dot / (na * nb)


class EmbeddingIndex:
    """オンライン cosine 類似度 index (brute-force)。"""

    def __init__(
        self,
        backend: EmbeddingBackend,
        *,
        threshold: float = 0.85,
    ) -> None:
        self._backend = backend
        self._threshold = threshold
        self._vectors: list[list[float]] = []

    @property
    def threshold(self) -> float:
        return self._threshold

    def seed_from_existing(self, prompts: list[str]) -> None:
        if not prompts:
            return
        self._vectors.extend(self._backend.embed(prompts))

    def is_similar(self, prompt: str) -> bool:
        if not self._vectors:
            return False
        vec = self._backend.embed([prompt])[0]
        for existing in self._vectors:
            if cosine_similarity(vec, existing) >= self._threshold:
                return True
        return False

    def add(self, prompt: str) -> None:
        self._vectors.append(self._backend.embed([prompt])[0])

    def __len__(self) -> int:
        return len(self._vectors)


def try_sentence_transformer_backend(model_name: str) -> EmbeddingBackend | None:
    """sentence-transformers が利用可能なら backend を返す。"""
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore[import-untyped]
    except ImportError:
        logger.info("sentence-transformers not installed; using FakeEmbeddingBackend")
        return None
    model = SentenceTransformer(model_name)

    class _STBackend:
        def embed(self, texts: list[str]) -> list[list[float]]:
            emb = model.encode(texts, normalize_embeddings=True)
            return [list(map(float, row)) for row in emb]

    return _STBackend()


__all__ = [
    "EmbeddingBackend",
    "EmbeddingIndex",
    "FakeEmbeddingBackend",
    "cosine_similarity",
    "try_sentence_transformer_backend",
]
