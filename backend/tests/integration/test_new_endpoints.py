from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from app.core.config import settings
from app.db.session import SessionLocal
from app.integrations.chroma_store import ChromaUpsertItem, ChromaVectorStore
from app.models.document import Document
from app.models.indexing_task import IndexingTask


async def _seed_documents(count: int) -> None:
    async with SessionLocal() as session:
        now = datetime.now(timezone.utc)
        docs: list[Document] = []
        for i in range(count):
            docs.append(
                Document(
                    id=f"seed-{i:05d}",
                    original_filename=f"f{i}.txt",
                    mime_type="text/plain",
                    size_bytes=10,
                    sha256=f"{i:064x}"[:64],
                    doc_type="text" if i % 3 == 0 else "markdown",
                    status="indexed" if i % 2 == 0 else "failed",
                    temp_path=f"./data/uploads/seed-{i:05d}/f{i}.txt",
                    error_message=None,
                    embedding_model_version=settings.embedding_model_version,
                    created_at=now - timedelta(seconds=i),
                    updated_at=now - timedelta(seconds=i),
                )
            )
        session.add_all(docs)
        await session.commit()


async def _seed_retry_tasks() -> None:
    async with SessionLocal() as session:
        session.add(
            Document(
                id="retry-doc-failed",
                original_filename="rf.txt",
                mime_type="text/plain",
                size_bytes=1,
                sha256="a" * 64,
                doc_type="text",
                status="failed",
                temp_path="./data/uploads/retry-doc-failed/rf.txt",
                error_message="boom",
                embedding_model_version=settings.embedding_model_version,
            )
        )
        session.add(
            IndexingTask(
                id="retry-task-failed",
                document_id="retry-doc-failed",
                status="failed",
                error_message="boom",
                celery_task_id="retry-task-failed",
            )
        )
        session.add(
            Document(
                id="retry-doc-ok",
                original_filename="ro.txt",
                mime_type="text/plain",
                size_bytes=1,
                sha256="b" * 64,
                doc_type="text",
                status="indexed",
                temp_path="./data/uploads/retry-doc-ok/ro.txt",
                error_message=None,
                embedding_model_version=settings.embedding_model_version,
            )
        )
        session.add(
            IndexingTask(
                id="retry-task-ok",
                document_id="retry-doc-ok",
                status="indexed",
                error_message=None,
                celery_task_id="retry-task-ok",
            )
        )
        await session.commit()


def test_healthz_fast_and_readyz_db_error(client):
    samples: list[float] = []
    for _ in range(10):
        t0 = datetime.now()
        response = client.get("/healthz")
        dt = (datetime.now() - t0).total_seconds() * 1000
        samples.append(dt)
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
    assert max(samples) < 50.0

    async def _broken_session_context():  # type: ignore[no-untyped-def]
        raise RuntimeError("db down")
        yield

    with patch("app.api.system.SessionLocal", _broken_session_context):
        response = client.get("/readyz")
    assert response.status_code == 503
    assert response.json()["error_code"] == "dependency_unavailable"


def test_documents_filter_and_pagination_with_10k(client):
    asyncio.run(_seed_documents(10_000))

    first = client.get("/api/v1/documents", params={"status": "indexed", "limit": 100})
    assert first.status_code == 200
    p1 = first.json()
    assert len(p1["items"]) == 100
    assert p1["next_cursor"] is not None
    assert all(item["status"] == "indexed" for item in p1["items"])

    second = client.get(
        "/api/v1/documents", params={"status": "indexed", "limit": 100, "cursor": p1["next_cursor"]}
    )
    assert second.status_code == 200
    p2 = second.json()
    ids1 = {item["document_id"] for item in p1["items"]}
    ids2 = {item["document_id"] for item in p2["items"]}
    assert len(ids2) == 100
    assert ids1.isdisjoint(ids2)


def test_delete_document_removes_db_and_chroma(client):
    doc_id = "delete-doc-1"
    store = ChromaVectorStore(
        host=settings.chroma_host,
        port=settings.chroma_port,
        persist_path=settings.chroma_persist_path,
        collection_name=f"kb_{settings.embedding_model_version}",
    )
    store.upsert_chunks(
        [
            ChromaUpsertItem(
                chunk_id="00000",
                doc_id=doc_id,
                text="to delete",
                embedding=[0.1] * 32,
                doc_type="text",
                doc_status="indexed",
                created_at=datetime.now(timezone.utc),
                embedding_model_version=settings.embedding_model_version,
            )
        ]
    )

    async def _seed() -> None:
        async with SessionLocal() as session:
            session.add(
                Document(
                    id=doc_id,
                    original_filename="del.txt",
                    mime_type="text/plain",
                    size_bytes=1,
                    sha256="c" * 64,
                    doc_type="text",
                    status="indexed",
                    temp_path="./data/uploads/delete-doc-1/del.txt",
                    error_message=None,
                    embedding_model_version=settings.embedding_model_version,
                )
            )
            await session.commit()

    asyncio.run(_seed())

    response = client.delete(f"/api/v1/documents/{doc_id}")
    assert response.status_code == 204
    assert client.get(f"/api/v1/documents/{doc_id}").status_code == 404
    assert len((store._collection.get(where={"doc_id": doc_id}).get("ids") or [])) == 0


def test_chat_history_cursor_and_reset(client):
    chat_id = "history-chat-1"
    for i in range(6):
        response = client.post("/api/v1/chat", json={"chat_id": chat_id, "text": f"msg {i}"})
        assert response.status_code == 200

    first = client.get(f"/api/v1/chat/{chat_id}/history", params={"limit": 3})
    assert first.status_code == 200
    p1 = first.json()
    assert len(p1["items"]) == 3
    assert p1["next_cursor"] is not None

    second = client.get(
        f"/api/v1/chat/{chat_id}/history", params={"limit": 3, "cursor": p1["next_cursor"]}
    )
    assert second.status_code == 200
    assert len(second.json()["items"]) == 3

    reset = client.post(f"/api/v1/chat/{chat_id}/reset")
    assert reset.status_code == 200
    assert reset.json()["deleted_messages"] >= 6

    empty = client.get(f"/api/v1/chat/{chat_id}/history", params={"limit": 3})
    assert empty.status_code == 200
    assert empty.json()["items"] == []

    # chat should still work after reset (messages deleted, chat_id reusable)
    after = client.post("/api/v1/chat", json={"chat_id": chat_id, "text": "after reset"})
    assert after.status_code == 200


def test_indexing_tasks_list_retry_cancel_and_system_info(client):
    asyncio.run(_seed_retry_tasks())

    listing = client.get("/api/v1/indexing-tasks", params={"limit": 20})
    assert listing.status_code == 200
    assert listing.json()["items"]
    assert all("celery_status" in item for item in listing.json()["items"])

    with patch("app.api.indexing_tasks.index_document.apply_async") as apply_async_mock:
        apply_async_mock.return_value.id = "new-retry-task-id"
        fail_retry = client.post("/api/v1/indexing-tasks/retry-task-ok/retry")
        ok_retry = client.post("/api/v1/indexing-tasks/retry-task-failed/retry")
    assert fail_retry.status_code == 400
    assert ok_retry.status_code == 200
    assert ok_retry.json()["status"] == "pending"

    doc_id = "cancel-doc-1"
    store = ChromaVectorStore(
        host=settings.chroma_host,
        port=settings.chroma_port,
        persist_path=settings.chroma_persist_path,
        collection_name=f"kb_{settings.embedding_model_version}",
    )
    store.upsert_chunks(
        [
            ChromaUpsertItem(
                chunk_id="00000",
                doc_id=doc_id,
                text="partial",
                embedding=[0.1] * 32,
                doc_type="text",
                doc_status="indexed",
                created_at=datetime.now(timezone.utc),
                embedding_model_version=settings.embedding_model_version,
            )
        ]
    )

    async def _seed_cancel() -> None:
        async with SessionLocal() as session:
            session.add(
                Document(
                    id=doc_id,
                    original_filename="cancel.txt",
                    mime_type="text/plain",
                    size_bytes=1,
                    sha256="d" * 64,
                    doc_type="text",
                    status="processing",
                    temp_path="./data/uploads/cancel-doc-1/cancel.txt",
                    error_message=None,
                    embedding_model_version=settings.embedding_model_version,
                )
            )
            session.add(
                IndexingTask(
                    id="cancel-task-1",
                    document_id=doc_id,
                    status="processing",
                    error_message=None,
                    celery_task_id="cancel-task-1",
                )
            )
            await session.commit()

    asyncio.run(_seed_cancel())

    with patch("app.api.indexing_tasks.celery_app.control.revoke") as revoke_mock:
        canceled = client.post("/api/v1/indexing-tasks/cancel-task-1/cancel")
    assert canceled.status_code == 200
    assert canceled.json()["status"] == "cancelled"
    revoke_mock.assert_called_once()
    status_doc = client.get(f"/api/v1/documents/{doc_id}")
    assert status_doc.status_code == 200
    assert status_doc.json()["status"] == "failed"
    assert len((store._collection.get(where={"doc_id": doc_id}).get("ids") or [])) == 0

    info = client.get("/system/info")
    assert info.status_code == 200
    payload = info.json()
    assert "embedding_model_version" in payload
    assert "use_fake_embeddings" in payload
    forbidden = {"hf_token", "chat_acl_secret", "database_url", "celery_broker_url"}
    assert forbidden.isdisjoint(set(payload.keys()))
