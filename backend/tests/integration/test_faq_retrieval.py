import pytest

# Cyrillic literals via unicode escapes for stable encoding on Windows CI.
QUERY_RESTORE = "\u043a\u0430\u043a \u0432\u043e\u0441\u0441\u0442\u0430\u043d\u043e\u0432\u0438\u0442\u044c \u0434\u043e\u0441\u0442\u0443\u043f?"
QUERY_TOPUP = "\u043a\u0430\u043a \u043f\u043e\u043f\u043e\u043b\u043d\u0438\u0442\u044c \u0441\u0447\u0435\u0442?"


@pytest.mark.asyncio
async def test_faq_restore_and_topup_with_rule_based_llm(monkeypatch: pytest.MonkeyPatch):
    from app.core.config import settings
    from app.integrations.chroma_store import ChromaVectorStore
    from app.services.embedding_factory import get_embedding_service
    from app.services.llm_client import RuleBasedLlmClient
    from app.services.rag_pipeline import RagPipeline
    from app.services.retriever import ChromaRetriever
    from tests.support.llm_factory_stubs import StubLlmFactory

    chroma_host = settings.chroma_host
    if not chroma_host:
        pytest.skip("Chroma is not configured (set CHROMA_HOST for live KB test)")

    monkeypatch.setattr(settings, "use_fake_embeddings", False)

    es = get_embedding_service()
    vs = ChromaVectorStore(
        host=chroma_host,
        port=settings.chroma_port,
        persist_path=settings.chroma_persist_path,
        collection_name=f"kb_{settings.embedding_model_version}",
    )
    pipeline = RagPipeline(
        retriever=ChromaRetriever(vector_store=vs, embedding_service=es),
        llm_factory=StubLlmFactory(RuleBasedLlmClient()),
    )

    restore, _ = await pipeline.answer(QUERY_RESTORE, "faq-restore")
    restore_sources = {source.doc_id for source in restore.sources}
    assert "instructions.access_to_personal_account" in restore_sources
    assert "\u043f\u043e\u043f\u043e\u043b\u043d" not in restore.text.casefold()
    assert "\u0432\u043e\u0441\u0441\u0442\u0430\u043d\u043e\u0432" in restore.text.casefold()

    topup, _ = await pipeline.answer(QUERY_TOPUP, "faq-topup")
    topup_sources = {source.doc_id for source in topup.sources}
    assert "instructions.account" in topup_sources
    assert "\u043f\u043e\u043f\u043e\u043b\u043d" in topup.text.casefold()
    assert "\u0432\u043e\u0441\u0441\u0442\u0430\u043d\u043e\u0432" not in topup.text.casefold()
