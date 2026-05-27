from __future__ import annotations

import asyncio

from app.core.config import settings
from app.integrations.chroma_store import ChromaVectorStore
from app.services.embedding_factory import get_embedding_service
from app.services.llm_client import RuleBasedLlmClient
from app.services.rag_pipeline import RagPipeline
from app.services.retriever import ChromaRetriever
from tests.support.llm_factory_stubs import StubLlmFactory


async def run_query(query: str) -> None:
    es = get_embedding_service()
    vs = ChromaVectorStore(
        host=settings.chroma_host,
        port=settings.chroma_port,
        persist_path=settings.chroma_persist_path,
        collection_name=f"kb_{settings.embedding_model_version}",
    )
    pipeline = RagPipeline(
        retriever=ChromaRetriever(vector_store=vs, embedding_service=es),
        llm_factory=StubLlmFactory(RuleBasedLlmClient()),
    )
    chunks = await pipeline.retriever.retrieve(query, settings.retriever_top_k)
    filtered = pipeline.filter_and_deduplicate(chunks)
    prompt = pipeline.build_prompt(query, filtered, [])
    response, _ = await pipeline.answer(query, f"local-{query[:8]}")
    with open("faq_pipeline_debug.txt", "a", encoding="utf-8") as fh:
        fh.write(f"\n===== {query} =====\n")
        fh.write("TOP CHUNKS:\n")
        for chunk in filtered[:3]:
            fh.write(f"- {chunk.doc_id} ({chunk.score}): {chunk.snippet[:200]}\n")
        fh.write("\nPROMPT:\n")
        fh.write(prompt[:2500])
        fh.write("\n\nANSWER:\n")
        fh.write(response.text)
        fh.write("\n\nSOURCES:\n")
        for source in response.sources:
            fh.write(f"- {source.doc_id}\n")


async def main() -> None:
    open("faq_pipeline_debug.txt", "w", encoding="utf-8").close()
    for query in ("как восстановить доступ?", "как пополнить счет?"):
        await run_query(query)


if __name__ == "__main__":
    asyncio.run(main())
