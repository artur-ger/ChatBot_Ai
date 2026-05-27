from __future__ import annotations

from app.core.config import settings
from app.integrations.chroma_store import ChromaVectorStore
from app.services.embedding_factory import get_embedding_service

QUERIES = [
    "как восстановить доступ?",
    "как пополнить счет?",
]


def main() -> None:
    es = get_embedding_service()
    vs = ChromaVectorStore(
        host=settings.chroma_host,
        port=settings.chroma_port,
        persist_path=settings.chroma_persist_path,
        collection_name=f"kb_{settings.embedding_model_version}",
    )
    col = vs._collection
    all_docs = col.get(include=["documents", "metadatas"])
    docs = all_docs.get("documents") or []
    metas = all_docs.get("metadatas") or []

    for needle in ("восстанов", "пополн", "доступ"):
        print(f"=== chunks containing '{needle}' ===")
        for doc, meta in zip(docs, metas, strict=False):
            if not doc or needle not in doc.casefold():
                continue
            doc_id = meta.get("doc_id", "?")
            preview = " ".join(doc.split())[:160]
            print(f"{doc_id}: {preview}")
        print()

    for query in QUERIES:
        vec = es.encode([query])[0]
        rows = vs.query(
            query_embedding=vec,
            top_k=5,
            embedding_model_version=settings.embedding_model_version,
        )
        print(f"=== vector top for: {query} ===")
        for doc_id, snippet, score, _meta in rows:
            preview = " ".join(snippet.split())[:160]
            print(f"{score:.3f} {doc_id}: {preview}")
        print()


if __name__ == "__main__":
    main()
