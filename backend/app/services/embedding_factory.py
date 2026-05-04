from __future__ import annotations

from app.core.config import settings
from app.services.embeddings import EmbeddingService
from app.services.fake_embeddings import FakeEmbeddingService


def get_embedding_service() -> EmbeddingService | FakeEmbeddingService:
    if settings.use_fake_embeddings:
        return FakeEmbeddingService(embedding_model_version=settings.embedding_model_version)
    return EmbeddingService(
        settings.embedding_model_name,
        embedding_model_version=settings.embedding_model_version,
    )
