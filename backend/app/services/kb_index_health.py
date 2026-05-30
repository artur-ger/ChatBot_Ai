from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import func, select

from app.core.config import settings
from app.db.session import SessionLocal
from app.integrations.chroma_store import ChromaVectorStore
from app.models.document import Document

KbIndexState = Literal["ok", "empty", "stale"]

_CACHE_TTL_SEC = 30.0
_cache: tuple[float, "KbIndexStatus"] | None = None


@dataclass(frozen=True)
class KbIndexStatus:
    state: KbIndexState
    indexed_documents: int
    chroma_chunks: int
    embedding_model_version: str
    message: str | None = None

    @property
    def is_searchable(self) -> bool:
        return self.state == "ok"


def evaluate_kb_index_state(*, indexed_documents: int, chroma_chunks: int) -> KbIndexState:
    if indexed_documents == 0:
        return "empty"
    if chroma_chunks == 0:
        return "stale"
    return "ok"


def _build_message(state: KbIndexState, *, indexed_documents: int, chroma_chunks: int) -> str | None:
    if state == "stale":
        return (
            "Векторный индекс пуст или устарел: в базе документов "
            f"{indexed_documents}, в Chroma чанков {chroma_chunks}. "
            "Запустите переиндексацию в админке (/admin → reindex)."
        )
    if state == "empty":
        return "База знаний пуста: загрузите документы в админке."
    return None


async def _count_indexed_documents() -> int:
    async with SessionLocal() as session:
        stmt = select(func.count()).select_from(Document).where(
            Document.status == "indexed",
            Document.embedding_model_version == settings.embedding_model_version,
        )
        result = await session.execute(stmt)
        return int(result.scalar_one() or 0)


def _count_chroma_chunks() -> int:
    store = ChromaVectorStore(
        host=settings.chroma_host,
        port=settings.chroma_port,
        persist_path=settings.chroma_persist_path,
        collection_name=f"kb_{settings.embedding_model_version}",
    )
    return store.count_chunks(embedding_model_version=settings.embedding_model_version)


async def get_kb_index_status(*, force: bool = False) -> KbIndexStatus:
    global _cache
    now = time.time()
    if not force and _cache is not None and now - _cache[0] < _CACHE_TTL_SEC:
        return _cache[1]

    indexed_documents = await _count_indexed_documents()
    chroma_chunks = await asyncio.to_thread(_count_chroma_chunks)
    state = evaluate_kb_index_state(
        indexed_documents=indexed_documents,
        chroma_chunks=chroma_chunks,
    )
    status = KbIndexStatus(
        state=state,
        indexed_documents=indexed_documents,
        chroma_chunks=chroma_chunks,
        embedding_model_version=settings.embedding_model_version,
        message=_build_message(state, indexed_documents=indexed_documents, chroma_chunks=chroma_chunks),
    )
    _cache = (now, status)
    return status


def clear_kb_index_status_cache() -> None:
    global _cache
    _cache = None
