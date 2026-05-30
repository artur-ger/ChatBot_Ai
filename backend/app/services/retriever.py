from dataclasses import dataclass
import asyncio
import re

from typing import Protocol

from app.integrations.chroma_store import ChromaVectorStore
from app.services.retrieval_rerank import (
    all_terms_match_score,
    heading_match_score,
    is_priority_instruction_chunk,
    lexical_overlap_score,
    phrase_in_text_score,
)


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


def rerank_retrieved_chunks(
    query: str,
    chunks: list[RetrievedChunk],
    *,
    lexical_weight: float = 0.45,
) -> list[RetrievedChunk]:
    if not chunks:
        return []

    vector_weight = 1.0 - lexical_weight
    ranked: list[tuple[float, RetrievedChunk]] = []
    for chunk in chunks:
        lexical = lexical_overlap_score(query, chunk.snippet)
        full_match = all_terms_match_score(query, chunk.snippet)
        heading = heading_match_score(query, chunk.snippet)
        phrase = phrase_in_text_score(query, chunk.snippet)
        combined = (
            vector_weight * chunk.score
            + lexical_weight * lexical
            + 0.15 * full_match
            + 0.35 * heading
            + 0.30 * phrase
        )
        combined = min(combined, 1.0)
        ranked.append(
            (
                combined,
                RetrievedChunk(
                    doc_id=chunk.doc_id,
                    snippet=chunk.snippet,
                    score=round(combined, 4),
                    doc_type=chunk.doc_type,
                    document_date=chunk.document_date,
                ),
            )
        )
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [chunk for _, chunk in ranked]


def _supplement_with_lexical_matches(
    query: str,
    chunks: list[RetrievedChunk],
    indexed_documents: list[tuple[str, str, dict]],
) -> list[RetrievedChunk]:
    terms = [term for term in re.findall(r"[\w\u0400-\u04FF]+", query.casefold()) if len(term) >= 3]
    if len(terms) < 2:
        return chunks

    if chunks and (
        heading_match_score(query, chunks[0].snippet) >= 0.85
        or phrase_in_text_score(query, chunks[0].snippet) >= 0.45
        or is_priority_instruction_chunk(query, chunks[0].doc_id, chunks[0].snippet)
    ):
        return chunks

    seen = {(chunk.doc_id, chunk.snippet) for chunk in chunks}
    extras: list[RetrievedChunk] = []
    for doc_id, snippet, metadata in indexed_documents:
        phrase = phrase_in_text_score(query, snippet)
        if not (
            is_priority_instruction_chunk(query, doc_id, snippet)
            or phrase >= 0.35
            or all_terms_match_score(query, snippet) >= 0.75
        ):
            continue
        key = (doc_id, snippet)
        if key in seen:
            continue
        seen.add(key)
        relevance = max(
            phrase,
            heading_match_score(query, snippet),
            all_terms_match_score(query, snippet),
        )
        extras.append(
            RetrievedChunk(
                doc_id=doc_id,
                snippet=snippet,
                score=min(0.97, 0.72 + relevance * 0.25),
                doc_type=str(metadata.get("doc_type", "")) or None,
                document_date=str(metadata.get("created_at", "")) or None,
            )
        )
    return chunks + extras


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
        candidate_k = min(max(top_k * 4, top_k), 40)
        rows = self.vector_store.query(
            query_embedding=vectors[0],
            top_k=candidate_k,
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
        indexed_documents = await asyncio.to_thread(
            self.vector_store.list_indexed_documents,
            embedding_model_version=self.embedding_service.embedding_model_version,
        )
        chunks = _supplement_with_lexical_matches(query, chunks, indexed_documents)
        reranked = rerank_retrieved_chunks(query, chunks)
        return reranked[:top_k]
