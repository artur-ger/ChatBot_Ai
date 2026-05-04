from dataclasses import dataclass
import asyncio

from typing import Protocol

from app.integrations.chroma_store import ChromaVectorStore


class EmbeddingEncoder(Protocol):
    model_name: str
    embedding_model_version: str

    def encode(self, texts: list[str]) -> list[list[float]]: ...


@dataclass
class RetrievedChunk:
    doc_id: str
    snippet: str
    score: float
    doc_type: str | None = None
    document_date: str | None = None


class BaseRetriever:
    async def retrieve(self, query: str, top_k: int) -> list[RetrievedChunk]:
        raise NotImplementedError


class InMemoryRetriever(BaseRetriever):
    def __init__(self) -> None:
        self._chunks = [
            RetrievedChunk(
                doc_id="doc-001",
                snippet="Поддержка работает с 9:00 до 18:00 по будням.",
                score=0.82,
            ),
            RetrievedChunk(
                doc_id="doc-002",
                snippet="Для возврата требуется номер заказа и причина.",
                score=0.71,
            ),
            RetrievedChunk(
                doc_id="doc-003",
                snippet="Ответ в чате должен содержать ссылки на источники.",
                score=0.69,
            ),
        ]

    async def retrieve(self, query: str, top_k: int) -> list[RetrievedChunk]:
        query_words = set(query.lower().split())
        ranked: list[tuple[float, RetrievedChunk]] = []
        for chunk in self._chunks:
            overlap = len(query_words & set(chunk.snippet.lower().split()))
            boost = overlap / 10.0
            ranked.append((chunk.score + boost, chunk))
        ranked.sort(key=lambda item: item[0], reverse=True)
        return [item[1] for item in ranked[:top_k]]


class ChromaRetriever(BaseRetriever):
    def __init__(
        self, *, vector_store: ChromaVectorStore, embedding_service: EmbeddingEncoder
    ) -> None:
        self.vector_store = vector_store
        self.embedding_service = embedding_service

    async def retrieve(self, query: str, top_k: int) -> list[RetrievedChunk]:
        vectors = await asyncio.to_thread(self.embedding_service.encode, [query])
        if not vectors:
            return []
        rows = self.vector_store.query(
            query_embedding=vectors[0],
            top_k=top_k,
            embedding_model_version=self.embedding_service.embedding_model_version,
        )
        chunks: list[RetrievedChunk] = []
        for doc_id, snippet, score, metadata in rows:
            chunks.append(
                RetrievedChunk(
                    doc_id=doc_id,
                    snippet=snippet,
                    score=score,
                    doc_type=str(metadata.get("doc_type", "")) or None,
                    document_date=str(metadata.get("created_at", "")) or None,
                )
            )
        return chunks
