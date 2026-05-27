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
    doc_ids = sorted({str(meta.get("doc_id", "")) for meta in all_docs["metadatas"]})
    with open("all_doc_ids.txt", "w", encoding="utf-8") as fh:
        for doc_id in doc_ids:
            fh.write(doc_id + "\n")

    restore_hits: list[str] = []
    for doc, meta in zip(all_docs["documents"], all_docs["metadatas"], strict=False):
        doc_id = str(meta.get("doc_id", ""))
        text = doc or ""
        lower = text.casefold()
        if "восстанов" in lower:
            restore_hits.append(f"{doc_id}: {text[:250].replace(chr(10), ' ')}")

    with open("restore_hits.txt", "w", encoding="utf-8") as fh:
        fh.write("\n\n".join(restore_hits))


if __name__ == "__main__":
    main()
