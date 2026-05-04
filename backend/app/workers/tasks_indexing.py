from __future__ import annotations

import hashlib
import hmac
import json
import shutil
import uuid
import asyncio
from datetime import datetime, timezone
from pathlib import Path

import httpx
from celery import Task
from sqlalchemy import select, update

from app.core.config import settings
from app.db.session import SessionLocal
from app.integrations.chroma_store import ChromaUpsertItem, ChromaVectorStore
from app.models.document import Document
from app.models.indexing_task import IndexingTask
from app.models.webhook_subscription import WebhookSubscription
from app.services.embedding_factory import get_embedding_service
from app.services.text_chunking import chunk_text
from app.services.text_extract import extract_text_from_file
from app.workers.async_runner import run_async
from app.workers.celery_app import celery_app


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _sign_payload(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def _send_webhook(*, url: str, secret: str | None, payload: dict[str, object]) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if secret:
        headers["X-Webhook-Signature"] = _sign_payload(secret, body)

    with httpx.Client(timeout=10.0) as client:
        for attempt in range(3):
            response = client.post(url, content=body, headers=headers)
            if 200 <= response.status_code < 300:
                return
            if attempt == 2:
                response.raise_for_status()


async def _index_document_async(document_id: str, task_id: str) -> None:
    embedding_service = get_embedding_service()
    vector_store = ChromaVectorStore(
        host=settings.chroma_host,
        port=settings.chroma_port,
        persist_path=settings.chroma_persist_path,
        collection_name=f"kb_{settings.embedding_model_version}",
    )

    webhook: WebhookSubscription | None = None

    async with SessionLocal() as session:
        document: Document | None = None
        task_row: IndexingTask | None = None
        for attempt in range(25):
            document = (
                await session.execute(select(Document).where(Document.id == document_id))
            ).scalar_one_or_none()
            task_row = (
                await session.execute(select(IndexingTask).where(IndexingTask.id == task_id))
            ).scalar_one_or_none()
            if document is not None and task_row is not None:
                break
            await asyncio.sleep(0.05 * (attempt + 1))

        if document is None or task_row is None:
            raise RuntimeError("Document or indexing task row not visible yet; retrying")

        assert task_row.id == task_id

        await session.execute(
            update(Document)
            .where(Document.id == document_id)
            .values(status="processing", error_message=None, updated_at=_utcnow())
        )
        await session.execute(
            update(IndexingTask)
            .where(IndexingTask.id == task_id)
            .values(status="processing", error_message=None, updated_at=_utcnow())
        )
        await session.commit()

        try:
            path = Path(document.temp_path)
            raw_text = extract_text_from_file(path=path, doc_type=document.doc_type)
            chunks = chunk_text(
                raw_text,
                chunk_size=settings.chunk_size,
                overlap=settings.chunk_overlap,
            )
            if not chunks:
                raise ValueError("No text extracted from document")

            embeddings = embedding_service.encode(chunks)
            now = _utcnow()

            upsert_items: list[ChromaUpsertItem] = []
            for idx, (chunk, vector) in enumerate(zip(chunks, embeddings, strict=True)):
                upsert_items.append(
                    ChromaUpsertItem(
                        chunk_id=f"{idx:05d}",
                        doc_id=document.id,
                        text=chunk,
                        embedding=vector,
                        doc_type=document.doc_type,
                        doc_status="indexed",
                        created_at=now,
                        embedding_model_version=settings.embedding_model_version,
                    )
                )

            vector_store.delete_document_chunks(document.id)
            vector_store.upsert_chunks(upsert_items)

            await session.execute(
                update(Document)
                .where(Document.id == document_id)
                .values(
                    status="indexed",
                    error_message=None,
                    embedding_model_version=settings.embedding_model_version,
                    updated_at=_utcnow(),
                )
            )
            await session.execute(
                update(IndexingTask)
                .where(IndexingTask.id == task_id)
                .values(status="indexed", error_message=None, updated_at=_utcnow())
            )

            webhook_result = await session.execute(
                select(WebhookSubscription).where(WebhookSubscription.document_id == document_id)
            )
            webhook = webhook_result.scalar_one_or_none()

            await session.commit()
            shutil.rmtree(path.parent, ignore_errors=True)

        except Exception as exc:
            await session.execute(
                update(Document)
                .where(Document.id == document_id)
                .values(status="failed", error_message=str(exc), updated_at=_utcnow())
            )
            await session.execute(
                update(IndexingTask)
                .where(IndexingTask.id == task_id)
                .values(status="failed", error_message=str(exc), updated_at=_utcnow())
            )
            webhook_result = await session.execute(
                select(WebhookSubscription).where(WebhookSubscription.document_id == document_id)
            )
            webhook = webhook_result.scalar_one_or_none()
            await session.commit()
            if webhook:
                payload_fail: dict[str, object] = {
                    "document_id": document_id,
                    "task_id": task_id,
                    "status": "failed",
                    "error": str(exc),
                }
                try:
                    _send_webhook(url=webhook.url, secret=webhook.secret, payload=payload_fail)
                except Exception:
                    pass
            raise

    if webhook:
        payload: dict[str, object] = {
            "document_id": document_id,
            "task_id": task_id,
            "status": "indexed",
        }
        try:
            _send_webhook(url=webhook.url, secret=webhook.secret, payload=payload)
        except Exception:
            # Webhook failures should not fail indexing; rely on polling as a fallback.
            pass


@celery_app.task(bind=True, name="index_document", max_retries=5, autoretry_for=(Exception,))  # type: ignore[untyped-decorator]
def index_document(self: Task, document_id: str, task_id: str) -> None:
    run_async(_index_document_async(document_id, task_id))


@celery_app.task(bind=True, name="reindex_documents", max_retries=3, autoretry_for=(Exception,))  # type: ignore[untyped-decorator]
def reindex_documents(self: Task, from_embedding_version: str, to_embedding_version: str) -> None:
    if from_embedding_version == to_embedding_version:
        return

    async def _load_ids() -> list[str]:
        async with SessionLocal() as session:
            result = await session.execute(
                select(Document.id).where(
                    Document.status == "indexed",
                    Document.embedding_model_version == from_embedding_version,
                )
            )
            return [row[0] for row in result.all()]

    document_ids = run_async(_load_ids())

    async def _enqueue(document_id_inner: str, new_task_id_inner: str) -> None:
        async with SessionLocal() as session:
            session.add(
                IndexingTask(
                    id=new_task_id_inner,
                    document_id=document_id_inner,
                    status="pending",
                )
            )
            await session.execute(
                update(Document)
                .where(Document.id == document_id_inner)
                .values(
                    status="pending",
                    embedding_model_version=to_embedding_version,
                    updated_at=_utcnow(),
                )
            )
            await session.commit()

    for document_id in document_ids:
        new_task_id = uuid.uuid4().hex
        run_async(_enqueue(document_id, new_task_id))
        run_async(_index_document_async(document_id, new_task_id))
