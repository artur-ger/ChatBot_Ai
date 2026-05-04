from __future__ import annotations

import math


class FakeEmbeddingService:
    def __init__(self, *, embedding_model_version: str) -> None:
        self.model_name = "fake-embedding-model"
        self.embedding_model_version = embedding_model_version

    def encode(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            seed = abs(hash(text)) % 997
            raw = [math.sin(seed + i) for i in range(32)]
            norm = math.sqrt(sum(value * value for value in raw)) or 1.0
            vectors.append([value / norm for value in raw])
        return vectors
