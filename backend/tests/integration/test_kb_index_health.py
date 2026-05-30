from unittest.mock import AsyncMock, patch

from app.services.kb_index_health import KbIndexStatus


def test_system_kb_index_endpoint(client):
    status = KbIndexStatus(
        state="ok",
        indexed_documents=5,
        chroma_chunks=120,
        embedding_model_version="all-MiniLM-L6-v2",
        message=None,
    )
    with patch(
        "app.api.system.get_kb_index_status",
        new=AsyncMock(return_value=status),
    ):
        response = client.get("/system/kb-index")

    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "ok"
    assert body["indexed_documents"] == 5
    assert body["chroma_chunks"] == 120


def test_system_info_includes_kb_index_fields(client):
    status = KbIndexStatus(
        state="stale",
        indexed_documents=10,
        chroma_chunks=0,
        embedding_model_version="all-MiniLM-L6-v2",
        message="reindex needed",
    )
    with patch(
        "app.api.system.get_kb_index_status",
        new=AsyncMock(return_value=status),
    ):
        response = client.get("/system/info")

    assert response.status_code == 200
    body = response.json()
    assert body["kb_index_state"] == "stale"
    assert body["kb_indexed_documents"] == 10
    assert body["kb_chroma_chunks"] == 0
    assert body["kb_index_message"] == "reindex needed"
