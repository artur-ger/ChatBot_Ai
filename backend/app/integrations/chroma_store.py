from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, cast

import chromadb
from chromadb.api.models.Collection import Collection


@dataclass(frozen=True)
class ChromaUpsertItem:
    chunk_id: str
    doc_id: str
    text: str
    embedding: list[float]
    doc_type: str
    doc_status: str
    created_at: datetime
    embedding_model_version: str


class ChromaVectorStore:
    def __init__(
        self,
        *,
        host: str | None,
        port: int,
        persist_path: str,
        collection_name: str,
    ) -> None:
        if host:
            self._client = chromadb.HttpClient(host=host, port=port)
        else:
            self._client = chromadb.PersistentClient(path=persist_path)
        self._collection: Collection = self._client.get_or_create_collection(name=collection_name)

    def upsert_chunks(self, items: list[ChromaUpsertItem]) -> None:
        ids: list[str] = []
        embeddings: list[list[float]] = []
        documents: list[str] = []
        metadatas: list[dict[str, Any]] = []

        for item in items:
            ids.append(f"{item.doc_id}:{item.chunk_id}")
            embeddings.append(item.embedding)
            documents.append(item.text)
            metadatas.append(
                {
                    "doc_id": item.doc_id,
                    "doc_type": item.doc_type,
                    "doc_status": item.doc_status,
                    "created_at": item.created_at.isoformat(),
                    "embedding_model_version": item.embedding_model_version,
                }
            )

        self._collection.upsert(
            ids=ids,
            embeddings=cast(Any, embeddings),
            documents=documents,
            metadatas=cast(Any, metadatas),
        )

    def delete_document_chunks(self, doc_id: str) -> None:
        self._collection.delete(where={"doc_id": doc_id})

    def query(
        self,
        *,
        query_embedding: list[float],
        top_k: int,
        embedding_model_version: str,
    ) -> list[tuple[str, str, float, dict[str, Any]]]:
        result = self._collection.query(
            query_embeddings=cast(Any, [query_embedding]),
            n_results=top_k,
            where={
                "$and": [
                    {"doc_status": "indexed"},
                    {"embedding_model_version": embedding_model_version},
                ]
            },
            include=["documents", "metadatas", "distances"],
        )

        out: list[tuple[str, str, float, dict[str, Any]]] = []
        ids_batch = result.get("ids") or []
        docs_batch = result.get("documents") or []
        meta_batch = result.get("metadatas") or []
        dist_batch = result.get("distances") or []

        if not ids_batch:
            return out

        ids = ids_batch[0] or []
        docs = (docs_batch[0] if docs_batch else []) or []
        metas = (meta_batch[0] if meta_batch else []) or []
        dists = (dist_batch[0] if dist_batch else []) or []

        for idx, chunk_id in enumerate(ids):
            raw_metadata = metas[idx] if idx < len(metas) else {}
            metadata = dict(raw_metadata) if isinstance(raw_metadata, Mapping) else {}
            doc_id = str(metadata.get("doc_id", ""))
            snippet = docs[idx] if idx < len(docs) else ""
            distance = float(dists[idx]) if idx < len(dists) else 1.0
            score = max(0.0, min(1.0, 1.0 / (1.0 + distance)))
            out.append((doc_id, snippet, score, metadata))

        return out

    def list_indexed_documents(
        self,
        *,
        embedding_model_version: str,
    ) -> list[tuple[str, str, dict[str, Any]]]:
        result = self._collection.get(
            where={
                "$and": [
                    {"doc_status": "indexed"},
                    {"embedding_model_version": embedding_model_version},
                ]
            },
            include=["documents", "metadatas"],
        )
        documents = result.get("documents") or []
        metadatas = result.get("metadatas") or []
        rows: list[tuple[str, str, dict[str, Any]]] = []
        for snippet, raw_metadata in zip(documents, metadatas, strict=False):
            metadata = dict(raw_metadata) if isinstance(raw_metadata, Mapping) else {}
            doc_id = str(metadata.get("doc_id", ""))
            if doc_id and snippet:
                rows.append((doc_id, snippet, metadata))
        return rows
