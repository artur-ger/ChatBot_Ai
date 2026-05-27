from __future__ import annotations

from app.core.config import settings
from app.integrations.chroma_store import ChromaVectorStore


def main() -> None:
    vs = ChromaVectorStore(
        host=settings.chroma_host,
        port=settings.chroma_port,
        persist_path=settings.chroma_persist_path,
        collection_name=f"kb_{settings.embedding_model_version}",
    )
    col = vs._collection
    all_docs = col.get(include=["documents", "metadatas"])
    needles = ("access", "восстанов", "personal", "popoln", "пополн")
    for doc, meta in zip(all_docs["documents"], all_docs["metadatas"], strict=False):
        doc_id = str(meta.get("doc_id", ""))
        text = doc or ""
        lower = text.casefold()
        if any(n in doc_id or n in lower for n in needles):
            print(f"--- {doc_id} ---")
            print(text[:400].replace("\n", " "))
            print()


if __name__ == "__main__":
    main()
