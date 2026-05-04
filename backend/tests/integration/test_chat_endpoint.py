from app.services.llm_client import BaseLlmClient
from app.services.rag_pipeline import RagPipeline
from app.services.retriever import BaseRetriever, RetrievedChunk
from app.core.chat_acl import make_chat_signature


class IntegrationRetriever(BaseRetriever):
    async def retrieve(self, query: str, top_k: int) -> list[RetrievedChunk]:
        return [RetrievedChunk(doc_id="doc-int", snippet="Тестовый сниппет.", score=0.88)]


class IntegrationLlm(BaseLlmClient):
    async def generate(self, prompt: str) -> str:
        return "Интеграционный ответ"


def test_chat_endpoint_contract_shape(client):
    client.app.state.rag_pipeline = RagPipeline(
        retriever=IntegrationRetriever(),
        llm_client=IntegrationLlm(),
    )

    chat_id = "chat-int"
    response = client.post(
        "/api/v1/chat",
        json={"text": "Тестовый вопрос", "chat_id": chat_id},
        headers={"X-Chat-Signature": make_chat_signature(chat_id, "test-chat-secret")},
    )
    payload = response.json()

    assert response.status_code == 200
    assert set(payload.keys()) == {"text", "sources", "confidence", "chat_id"}
    assert payload["chat_id"] == chat_id
    assert isinstance(payload["sources"], list)
    assert payload["sources"][0]["doc_id"] == "doc-int"
    assert payload["sources"][0]["doc_type"] is None
