from datetime import datetime, timezone
from unittest.mock import MagicMock

from app.integrations.chroma_store import ChromaUpsertItem, ChromaVectorStore


def test_count_chunks_uses_total_collection_count():
    store = ChromaVectorStore.__new__(ChromaVectorStore)
    store._collection = MagicMock()
    store._collection.count.return_value = 42

    assert store.count_chunks(embedding_model_version="all-MiniLM-L6-v2") == 42
    store._collection.count.assert_called_once_with()


def test_has_document_chunks():
    store = ChromaVectorStore.__new__(ChromaVectorStore)
    store._collection = MagicMock()
    store._collection.get.return_value = {"ids": ["doc:00000"]}

    assert store.has_document_chunks("doc") is True
    store._collection.get.assert_called_once_with(where={"doc_id": "doc"}, include=[])


def test_upsert_item_shape():
    item = ChromaUpsertItem(
        chunk_id="00001",
        doc_id="doc-1",
        text="hello",
        embedding=[0.1, 0.2],
        doc_type="text",
        doc_status="indexed",
        created_at=datetime.now(timezone.utc),
        embedding_model_version="v1",
    )
    assert item.doc_id == "doc-1"
