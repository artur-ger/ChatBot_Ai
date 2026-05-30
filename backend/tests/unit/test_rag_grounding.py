from app.services.rag_grounding import (
    INSUFFICIENT_ANSWER_TEXT,
    extract_grounded_answer,
    is_likely_hallucination,
    should_use_extractive_answer,
)
from app.services.retrieval_rerank import phrase_in_text_score
from app.services.retriever import RetrievedChunk


CFA_SNIPPET = (
    "Возможные варианты учета ЦФА в зависимости от срока обращения у инвестора: "
    "по счету 06 «Долгосрочные финансовые вложения» (если срок обращения ЦФА превышает 12 месяцев); "
    "по счету 58 «Краткосрочные финансовые вложения» (если срок обращения ЦФА меньше 12 месяцев)."
)

CFA_QUESTION = "Какие варианты учета ЦФА в зависимости от срока обращения у инвестора"


def test_phrase_in_text_score_finds_accounting_chunk():
    score = phrase_in_text_score(CFA_QUESTION, CFA_SNIPPET)
    assert score >= 0.45


def test_should_use_extractive_answer_for_cfa_question():
    chunks = [RetrievedChunk(doc_id="books.accounting", snippet=CFA_SNIPPET, score=0.7)]
    assert should_use_extractive_answer(CFA_QUESTION, chunks)


def test_extract_grounded_answer_returns_accounts():
    chunks = [
        RetrievedChunk(doc_id="books.accounting", snippet=CFA_SNIPPET, score=0.7),
        RetrievedChunk(
            doc_id="books.accounting",
            snippet="скрыть в отчетности выбранный способ учета ЦФА",
            score=0.85,
        ),
    ]
    answer = extract_grounded_answer(CFA_QUESTION, chunks)
    assert answer is not None
    assert "06" in answer
    assert "58" in answer
    assert "fifo" not in answer.casefold()


def test_detects_hallucinated_fifo_answer():
    context = CFA_SNIPPET
    answer = (
        "Конкретно не указано. Однако исходя из общего понимания возможны подходы FIFO и LIFO."
    )
    assert is_likely_hallucination(answer, context)


def test_grounded_short_answer_is_not_flagged():
    answer = "Учет ведется по счету 06 или 58 в зависимости от срока обращения."
    assert not is_likely_hallucination(answer, CFA_SNIPPET)


def test_insufficient_answer_constant():
    assert "нет точного ответа" in INSUFFICIENT_ANSWER_TEXT.lower()
