from unittest.mock import AsyncMock, patch

import pytest

from app.services.kb_index_health import KbIndexStatus
from app.services.llm_client import BaseLlmClient
from app.services.rag_grounding import INSUFFICIENT_ANSWER_TEXT
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


class HallucinatingLlm(BaseLlmClient):
    async def generate(self, prompt: str) -> str:
        return (
            "Конкретно не указано. Однако исходя из общего понимания возможны подходы FIFO и LIFO."
        )


class CfaRetriever(BaseRetriever):
    async def retrieve(self, query: str, top_k: int) -> list[RetrievedChunk]:
        return [
            RetrievedChunk(
                doc_id="books.accounting",
                snippet=(
                    "Возможные варианты учета ЦФА в зависимости от срока обращения у инвестора: "
                    "по счету 06 «Долгосрочные финансовые вложения» (если срок обращения ЦФА превышает 12 месяцев); "
                    "по счету 58 «Краткосрочные финансовые вложения» (если срок обращения ЦФА меньше 12 месяцев)."
                ),
                score=0.85,
            )
        ][:top_k]


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
async def test_answer_reports_stale_index_before_retrieval():
    pipeline = RagPipeline(retriever=StubRetriever(), llm_factory=StubLlmFactory(StubLlm()))
    stale = KbIndexStatus(
        state="stale",
        indexed_documents=100,
        chroma_chunks=0,
        embedding_model_version="all-MiniLM-L6-v2",
        message="Векторный индекс пуст.",
    )
    with patch(
        "app.services.rag_pipeline.get_kb_index_status",
        new=AsyncMock(return_value=stale),
    ):
        response, scores = await pipeline.answer("Как учитываются ЦФА?", "chat-1")

    assert scores == []
    assert "индекс" in response.text.lower()
    assert response.confidence == 0.0
    assert response.sources == []


@pytest.mark.asyncio
async def test_answer_fallback_when_llm_unavailable():
    pipeline = RagPipeline(retriever=StubRetriever(), llm_factory=StubLlmFactory(FailingLlm()))
    ok_index = KbIndexStatus(
        state="ok",
        indexed_documents=1,
        chroma_chunks=1,
        embedding_model_version="all-MiniLM-L6-v2",
        message=None,
    )
    with patch(
        "app.services.rag_pipeline.get_kb_index_status",
        new=AsyncMock(return_value=ok_index),
    ):
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
    assert "Не указывай источники" in prompt
    assert "Контекст" in prompt
    assert INSUFFICIENT_ANSWER_TEXT in prompt


@pytest.mark.asyncio
async def test_answer_uses_extractive_response_for_strong_cfa_match():
    pipeline = RagPipeline(retriever=CfaRetriever(), llm_factory=StubLlmFactory(HallucinatingLlm()))
    ok_index = KbIndexStatus(
        state="ok",
        indexed_documents=1,
        chroma_chunks=1,
        embedding_model_version="all-MiniLM-L6-v2",
        message=None,
    )
    with patch(
        "app.services.rag_pipeline.get_kb_index_status",
        new=AsyncMock(return_value=ok_index),
    ):
        response, _scores = await pipeline.answer(
            "Какие варианты учета ЦФА в зависимости от срока обращения у инвестора",
            "chat-cfa",
        )

    assert "06" in response.text
    assert "58" in response.text
    assert "fifo" not in response.text.casefold()


@pytest.mark.asyncio
async def test_answer_replaces_hallucination_with_grounded_or_insufficient():
    pipeline = RagPipeline(
        retriever=StubRetriever(),
        llm_factory=StubLlmFactory(HallucinatingLlm()),
    )
    ok_index = KbIndexStatus(
        state="ok",
        indexed_documents=1,
        chroma_chunks=1,
        embedding_model_version="all-MiniLM-L6-v2",
        message=None,
    )
    with patch(
        "app.services.rag_pipeline.get_kb_index_status",
        new=AsyncMock(return_value=ok_index),
    ):
        response, _scores = await pipeline.answer("Как оплатить заказ?", "chat-1")

    assert "fifo" not in response.text.casefold()
    assert response.text


def test_sanitize_answer_text_removes_sources_and_citations():
    from app.services.chat_presenter import sanitize_user_answer_text

    raw = (
        "ЦФА учитываются при реализации.\n\n"
        "Источники: [books.taxation], [books.risk_hedging]\n\n"
        "Уверенность: 1.00"
    )
    cleaned = sanitize_user_answer_text(raw)
    assert cleaned == "ЦФА учитываются при реализации."
