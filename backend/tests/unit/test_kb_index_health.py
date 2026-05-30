from app.services.kb_index_health import evaluate_kb_index_state


def test_empty_when_no_indexed_documents():
    assert evaluate_kb_index_state(indexed_documents=0, chroma_chunks=0) == "empty"
    assert evaluate_kb_index_state(indexed_documents=0, chroma_chunks=100) == "empty"


def test_stale_when_indexed_but_no_chunks():
    assert evaluate_kb_index_state(indexed_documents=5052, chroma_chunks=0) == "stale"


def test_ok_when_both_present():
    assert evaluate_kb_index_state(indexed_documents=10, chroma_chunks=50) == "ok"
