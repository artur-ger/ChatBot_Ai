from __future__ import annotations

from app.core.config import settings
from app.integrations.chroma_store import ChromaVectorStore
from app.services.embedding_factory import get_embedding_service
from app.services.retrieval_rerank import lexical_overlap_score


def main() -> None:
    query = "как восстановить доступ?"
    es = get_embedding_service()
    vs = ChromaVectorStore(
        host=settings.chroma_host,
        port=settings.chroma_port,
        persist_path=settings.chroma_persist_path,
        collection_name=f"kb_{settings.embedding_model_version}",
    )
    vec = es.encode([query])[0]
    rows = vs.query(
        query_embedding=vec,
        top_k=40,
        embedding_model_version=settings.embedding_model_version,
    )
    with open("restore_candidates.txt", "w", encoding="utf-8") as fh:
        for i, (doc_id, snippet, score, _meta) in enumerate(rows, start=1):
            lex = lexical_overlap_score(query, snippet)
            fh.write(
                f"{i:02d} vec={score:.3f} lex={lex:.2f} {doc_id}\n"
                f"  {snippet[:180].replace(chr(10), ' ')}\n\n"
            )
            if doc_id == "instructions.access_to_personal_account":
                fh.write(">>> FOUND TARGET <<<\n\n")


if __name__ == "__main__":
    main()
