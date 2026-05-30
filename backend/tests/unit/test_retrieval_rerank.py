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


def test_rerank_prefers_phrase_match_over_vector_score():
    chunks = [
        RetrievedChunk(
            doc_id="books.accounting",
            snippet="скрыть в отчетности выбранный способ учета ЦФА",
            score=0.91,
        ),
        RetrievedChunk(
            doc_id="books.accounting",
            snippet=(
                "Возможные варианты учета ЦФА в зависимости от срока обращения у инвестора: "
                "по счету 06 и 58."
            ),
            score=0.84,
        ),
    ]
    reranked = rerank_retrieved_chunks(
        "Какие варианты учета ЦФА в зависимости от срока обращения у инвестора",
        chunks,
    )
    assert "06" in reranked[0].snippet
