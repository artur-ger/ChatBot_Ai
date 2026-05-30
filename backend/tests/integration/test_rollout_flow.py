from unittest.mock import AsyncMock, patch

import app.api.admin_login as admin_login_module
import app.core.admin_auth as admin_auth_module
import app.core.config as config_module
from app.services.kb_index_health import KbIndexStatus
from app.services.llm_client import RuleBasedLlmClient
from app.services.rag_pipeline import RagPipeline
from app.services.retriever import BaseRetriever, RetrievedChunk
from tests.support.llm_factory_stubs import StubLlmFactory


class FixedRetriever(BaseRetriever):
    async def retrieve(self, query: str, top_k: int) -> list[RetrievedChunk]:
        return [
            RetrievedChunk(
                doc_id="documents.law115",
                snippet="Federal law 115-FZ on counteracting money laundering.",
                score=0.88,
            )
        ][:top_k]


def test_chat_hides_sources_and_confidence_from_client(client):
    stub_factory = StubLlmFactory(RuleBasedLlmClient(), model_name="rule-based-llm")
    client.app.state.llm_factory = stub_factory
    client.app.state.rag_pipeline = RagPipeline(
        retriever=FixedRetriever(),
        llm_factory=stub_factory,
    )
    kb_ok = KbIndexStatus(
        state="ok",
        indexed_documents=1,
        chroma_chunks=1,
        embedding_model_version="test",
        message=None,
    )

    with patch(
        "app.services.rag_pipeline.get_kb_index_status",
        new=AsyncMock(return_value=kb_ok),
    ):
        response = client.post(
            "/api/v1/chat",
            json={"text": "What is law115?", "chat_id": "kb-flow-test"},
        )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["chat_id"] == "kb-flow-test"
    assert data["sources"] == []
    assert data["confidence"] == 0.0
    assert data["text"]
    assert "Источники" not in data["text"]


def test_admin_cookie_can_list_indexed_documents(client, monkeypatch):
    old_settings = config_module.settings
    old_admin_auth_settings = admin_auth_module.settings
    old_admin_login_settings = admin_login_module.settings

    try:
        monkeypatch.setenv("ADMIN_API_AUTH_DISABLED", "false")
        monkeypatch.setenv("ADMIN_USERNAME", "admin")
        monkeypatch.setenv("ADMIN_PASSWORD", "pass123")
        monkeypatch.setenv("ADMIN_SESSION_SECRET", "test-session-secret")

        patched_settings = config_module.Settings()
        config_module.settings = patched_settings
        admin_auth_module.settings = patched_settings
        admin_login_module.settings = patched_settings

        login = client.post(
            "/api/v1/admin/login",
            json={"username": "admin", "password": "pass123"},
        )
        assert login.status_code == 200, login.text

        docs = client.get("/api/v1/documents?limit=10")
        assert docs.status_code == 200, docs.text
        assert "items" in docs.json()
    finally:
        config_module.settings = old_settings
        admin_auth_module.settings = old_admin_auth_settings
        admin_login_module.settings = old_admin_login_settings
