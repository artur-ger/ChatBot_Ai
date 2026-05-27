from __future__ import annotations

from app.core.config import settings
from app.integrations.chroma_store import ChromaVectorStore
from app.services.embedding_factory import get_embedding_service
from app.services.retriever import ChromaRetriever, rerank_retrieved_chunks

QUERIES = [
    "как восстановить доступ?",
    "как пополнить счет?",
]


async def main() -> None:
    import asyncio

    es = get_embedding_service()
    vs = ChromaVectorStore(
        host=settings.chroma_host,
        port=settings.chroma_port,
        persist_path=settings.chroma_persist_path,
        collection_name=f"kb_{settings.embedding_model_version}",
    )
    retriever = ChromaRetriever(vector_store=vs, embedding_service=es)

    for query in QUERIES:
        chunks = await retriever.retrieve(query, top_k=5)
        print(f"=== reranked top for: {query} ===")
        for chunk in chunks:
            preview = " ".join(chunk.snippet.split())[:160]
            print(f"{chunk.score:.3f} {chunk.doc_id}: {preview}")
        print()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
