from __future__ import annotations

from app.core.config import settings
from app.integrations.chroma_store import ChromaVectorStore

TARGETS = [
    "instructions.access_to_personal_account",
    "instructions.often_questions",
    "instructions.instrukciya_fizlic",
    "books.accounting",
]


def main() -> None:
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

    for doc_id in TARGETS:
        print(f"\n{'=' * 20} {doc_id} {'=' * 20}")
        for doc, meta in zip(docs, metas, strict=False):
            if meta.get("doc_id") != doc_id:
                continue
            print(doc[:1200])
            print("---")


if __name__ == "__main__":
    main()
