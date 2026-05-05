from app.services.llm_client import BaseLlmClient, RuleBasedLlmClient
from app.services.rag_pipeline import RagPipeline
from app.services.retriever import BaseRetriever, RetrievedChunk


class SmokeRetriever(BaseRetriever):
    async def retrieve(self, query: str, top_k: int) -> list[RetrievedChunk]:
        return [
            RetrievedChunk(
                doc_id="doc-1", snippet="Поддержка работает с 9:00 до 18:00 по будням.", score=0.9
            ),
        ][:top_k]


class FailingLlm(BaseLlmClient):
    async def generate(self, prompt: str) -> str:
        raise TimeoutError("boom")


def test_smoke_successful_chat_flow(client):
    client.app.state.rag_pipeline = RagPipeline(
        retriever=SmokeRetriever(),
        llm_client=RuleBasedLlmClient(),
    )

    chat_id = "smoke-1"
    response = client.post(
        "/api/v1/chat",
        json={"text": "Какие часы работы поддержки?", "chat_id": chat_id},
    )
    data = response.json()

    assert response.status_code == 200
    assert data["chat_id"] == chat_id
    assert isinstance(data["sources"], list)
    assert 0.0 <= data["confidence"] <= 1.0


def test_smoke_degradation_when_llm_down(client):
    client.app.state.rag_pipeline = RagPipeline(
        retriever=SmokeRetriever(),
        llm_client=FailingLlm(),
    )

    chat_id = "smoke-2"
    response = client.post(
        "/api/v1/chat",
        json={"text": "trigger_llm_down", "chat_id": chat_id},
    )
    data = response.json()

    assert response.status_code == 200
    assert "временно недоступен" in data["text"].lower()
    assert data["chat_id"] == chat_id
