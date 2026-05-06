from __future__ import annotations

from functools import lru_cache
from typing import cast

@lru_cache(maxsize=1)
def _load_model(model_name: str):
    # Lazy import so local runs with fake embeddings do not require heavy ML deps.
    from sentence_transformers import SentenceTransformer

    return cast(SentenceTransformer, SentenceTransformer(model_name))


class EmbeddingService:
    def __init__(self, model_name: str, *, embedding_model_version: str) -> None:
        self.model_name = model_name
        self.embedding_model_version = embedding_model_version
        self._model = _load_model(model_name)

    def encode(self, texts: list[str]) -> list[list[float]]:
        vectors = self._model.encode(
            texts,
            batch_size=32,
            show_progress_bar=False,
            normalize_embeddings=True,
        )
        return [vector.tolist() for vector in vectors]
