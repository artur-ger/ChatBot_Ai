from app.services.retrieval_rerank import all_terms_match_score, lexical_overlap_score
from app.services.retriever import RetrievedChunk, rerank_retrieved_chunks


def test_lexical_overlap_prefers_matching_terms():
    restore_score = lexical_overlap_score(
        "как восстановить доступ?",
        "Как восстановить доступ в личный кабинет? Нажмите восстановить пароль.",
    )
    topup_score = lexical_overlap_score(
        "как восстановить доступ?",
        "Как пополнить счет? Перейдите в раздел пополнения баланса.",
    )
    assert restore_score > topup_score


def test_all_terms_match_prefers_full_query_match():
    full = all_terms_match_score(
        "как восстановить доступ?",
        "Как восстановить доступ в личный кабинет?",
    )
    partial = all_terms_match_score(
        "как восстановить доступ?",
        "Компании получают доступ к инвесторам.",
    )
    assert full == 1.0
    assert partial < 1.0


def test_rerank_swaps_wrong_vector_order():
    chunks = [
        RetrievedChunk(
            doc_id="instructions.instrukciya_fizlic",
            snippet="Как пополнить счет? Ответ: перейдите в раздел пополнения.",
            score=0.91,
        ),
        RetrievedChunk(
            doc_id="instructions.access_to_personal_account",
            snippet="Как восстановить доступ в личный кабинет? Нажмите восстановить пароль.",
            score=0.88,
        ),
    ]
    reranked = rerank_retrieved_chunks("как восстановить доступ?", chunks)
    assert reranked[0].doc_id == "instructions.access_to_personal_account"
