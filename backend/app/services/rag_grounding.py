from __future__ import annotations

import re

from app.services.rag_answer_extract import extract_faq_answer, extract_relevant_excerpt
from app.services.retrieval_rerank import (
    all_terms_match_score,
    heading_match_score,
    lexical_overlap_score,
    phrase_in_text_score,
)
from app.services.retriever import RetrievedChunk

_UNGROUNDED_MARKERS = (
    "исходя из общего понимания",
    "исходя из общих",
    "возможны следующие подходы",
    "может потребоваться уточнение",
    "не указано конкретно",
    "не указаны конкретно",
    "fifo",
    "lifo",
    "first in first out",
    "last in first out",
    "в общем порядке",
    "типичный подход",
    "как правило, такие",
)

_TERM_RE = re.compile(r"[\w\u0400-\u04FF]+", re.UNICODE)
_STOPWORDS = frozenset(
    {
        "как",
        "что",
        "где",
        "или",
        "для",
        "при",
        "это",
        "ли",
        "не",
        "на",
        "в",
        "и",
        "а",
        "у",
        "по",
        "из",
        "к",
        "с",
        "о",
        "об",
        "от",
        "до",
        "за",
        "какие",
        "какой",
        "какая",
        "какое",
        "the",
        "and",
    }
)

INSUFFICIENT_ANSWER_TEXT = "В базе знаний нет точного ответа на этот вопрос."


def _merge_same_doc_snippets(chunks: list[RetrievedChunk], doc_id: str) -> str:
    parts: list[str] = []
    seen: set[str] = set()
    for chunk in chunks:
        if chunk.doc_id != doc_id:
            continue
        snippet = chunk.snippet.strip()
        if not snippet or snippet in seen:
            continue
        seen.add(snippet)
        parts.append(snippet)
    return " ".join(parts)


def _answer_terms(answer: str) -> set[str]:
    terms = {
        word.casefold()
        for word in _TERM_RE.findall(answer)
        if len(word) >= 4 and word.casefold() not in _STOPWORDS
    }
    return terms


def grounding_overlap(answer: str, context: str) -> float:
    answer_terms = _answer_terms(answer)
    if not answer_terms:
        return 0.0
    context_cf = context.casefold()
    hits = sum(1 for term in answer_terms if term in context_cf or term[:5] in context_cf)
    return hits / len(answer_terms)


def is_likely_hallucination(answer: str, context: str) -> bool:
    answer_cf = answer.casefold()
    context_cf = context.casefold()
    for marker in _UNGROUNDED_MARKERS:
        if marker in answer_cf and marker not in context_cf:
            return True
    overlap = grounding_overlap(answer, context)
    if len(answer) > 120 and overlap < 0.22:
        return True
    if len(answer) > 80 and overlap < 0.15:
        return True
    return False


def chunk_relevance_score(question: str, chunk: RetrievedChunk) -> float:
    return max(
        phrase_in_text_score(question, chunk.snippet),
        heading_match_score(question, chunk.snippet),
        all_terms_match_score(question, chunk.snippet),
        lexical_overlap_score(question, chunk.snippet),
    )


def extract_grounded_answer(question: str, chunks: list[RetrievedChunk]) -> str | None:
    if not chunks:
        return None

    ranked: list[tuple[float, RetrievedChunk]] = [
        (chunk_relevance_score(question, chunk), chunk) for chunk in chunks
    ]
    ranked.sort(key=lambda item: item[0], reverse=True)
    best_score, best_chunk = ranked[0]

    combined_context = "\n".join(chunk.snippet for chunk in chunks[:3])
    faq_answer = extract_faq_answer(question, combined_context)
    if faq_answer and best_score < 0.85:
        return faq_answer

    if best_score >= 0.45:
        merged = _merge_same_doc_snippets(chunks, best_chunk.doc_id)
        snippet = merged if len(merged) > len(best_chunk.snippet) else best_chunk.snippet
        return extract_relevant_excerpt(question, snippet)

    if faq_answer:
        return faq_answer

    return None


def should_use_extractive_answer(question: str, chunks: list[RetrievedChunk]) -> bool:
    if not chunks:
        return False
    best = max(chunk_relevance_score(question, chunk) for chunk in chunks[:3])
    return best >= 0.72
