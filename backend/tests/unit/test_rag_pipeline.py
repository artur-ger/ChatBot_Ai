import pytest

from app.services.llm_client import BaseLlmClient
from app.services.rag_prompt_defaults import DEFAULT_RAG_SYSTEM_INSTRUCTION
from app.services.rag_pipeline import RagPipeline
from app.services.retriever import BaseRetriever, RetrievedChunk
from tests.support.llm_factory_stubs import StubLlmFactory


class StubRetriever(BaseRetriever):
    async def retrieve(self, query: str, top_k: int) -> list[RetrievedChunk]:
        return [
            RetrievedChunk(doc_id="doc-1", snippet="Оплата доступна картой.", score=0.9),
            RetrievedChunk(doc_id="doc-1", snippet="Оплата доступна картой.", score=0.9),
            RetrievedChunk(doc_id="doc-2", snippet="Доставка 2-3 дня.", score=0.2),
        ][:top_k]


class StubLlm(BaseLlmClient):
    async def generate(self, prompt: str) -> str:
        return f"ok::{prompt[:30]}"


class FailingLlm(BaseLlmClient):
    async def generate(self, prompt: str) -> str:
        raise TimeoutError("boom")


@pytest.mark.asyncio
async def test_filter_and_dedup_and_confidence():
    pipeline = RagPipeline(retriever=StubRetriever(), llm_factory=StubLlmFactory(StubLlm()))
    chunks = await pipeline.retriever.retrieve("оплата", 5)
    filtered = pipeline.filter_and_deduplicate(chunks)

    assert len(filtered) == 1
    assert filtered[0].doc_id == "doc-1"
    assert pipeline.calculate_confidence(filtered) == 0.9


@pytest.mark.asyncio
async def test_answer_fallback_when_llm_unavailable():
    pipeline = RagPipeline(retriever=StubRetriever(), llm_factory=StubLlmFactory(FailingLlm()))
    response, _scores = await pipeline.answer("Как оплатить заказ?", "chat-1")

    assert response.chat_id == "chat-1"
    assert "временно недоступен" in response.text.lower()
    assert len(response.sources) == 1


def test_normalize_query():
    pipeline = RagPipeline(retriever=StubRetriever(), llm_factory=StubLlmFactory(StubLlm()))
    assert pipeline.normalize_query("  Привет   мир  ") == "Привет мир"


def test_build_prompt_uses_custom_instruction():
    pipeline = RagPipeline(retriever=StubRetriever(), llm_factory=StubLlmFactory(StubLlm()))
    chunks = [
        RetrievedChunk(doc_id="doc-1", snippet="Оплата картой.", score=0.9),
    ]
    prompt = pipeline.build_prompt(
        "Как оплатить?",
        chunks,
        [("user", "Привет")],
        system_instruction="Кастомная инструкция.",
    )
    assert prompt.startswith("Кастомная инструкция.")
    assert "История (если есть):" in prompt
    assert "[doc-1] Оплата картой." in prompt
    assert "Вопрос: Как оплатить?" in prompt


def test_build_prompt_default_instruction():
    pipeline = RagPipeline(retriever=StubRetriever(), llm_factory=StubLlmFactory(StubLlm()))
    prompt = pipeline.build_prompt("Вопрос?", [], [])
    assert prompt.startswith(DEFAULT_RAG_SYSTEM_INSTRUCTION)
