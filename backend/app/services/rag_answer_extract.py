from __future__ import annotations

import re

from app.services.retrieval_rerank import (
    all_terms_match_score,
    heading_match_score,
    lexical_overlap_score,
    significant_query_phrases,
)

_QUESTION_MARKER = "Вопрос:"
_CONTEXT_MARKER = "Контекст:"
_CHUNK_RE = re.compile(r"\[([^\]]+)\]\s*(.*?)(?=\n\[|$)", re.DOTALL)


def extract_question_from_prompt(prompt: str) -> str:
    if _QUESTION_MARKER not in prompt:
        return prompt.strip()
    return prompt.rsplit(_QUESTION_MARKER, maxsplit=1)[-1].strip()


def extract_context_chunks_from_prompt(prompt: str) -> list[tuple[str, str]]:
    if _CONTEXT_MARKER not in prompt:
        return []
    context_block = prompt.split(_CONTEXT_MARKER, maxsplit=1)[1]
    if _QUESTION_MARKER in context_block:
        context_block = context_block.rsplit(_QUESTION_MARKER, maxsplit=1)[0]
    chunks: list[tuple[str, str]] = []
    for match in _CHUNK_RE.finditer(context_block):
        doc_id = match.group(1).strip()
        snippet = match.group(2).strip()
        if doc_id and snippet:
            chunks.append((doc_id, snippet))
    return chunks


def extract_faq_answer(question: str, text: str) -> str | None:
    best_score = 0.0
    best_answer: str | None = None

    for block in re.split(r"(?i)вопрос:\s*", text):
        if "ответ:" not in block.casefold():
            continue
        question_part, answer_part = re.split(r"(?i)ответ:\s*", block, maxsplit=1)
        faq_question = question_part.strip()
        faq_answer = re.split(r"(?i)вопрос:", answer_part, maxsplit=1)[0].strip()
        if not faq_question or not faq_answer:
            continue
        overlap = all_terms_match_score(question, faq_question)
        if overlap > best_score:
            best_score = overlap
            best_answer = faq_answer

    if best_score >= 0.65 and best_answer:
        return _normalize_answer(best_answer)
    return None


def _normalize_answer(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    cleaned = _trim_incomplete_tail(cleaned)
    if len(cleaned) > 1800:
        cleaned = _truncate_at_sentence_boundary(cleaned, 1800)
    return cleaned


def _ends_complete_sentence(text: str) -> bool:
    return bool(re.search(r'(?:[.!?»][\s"»)]*|\)\.)$', text.strip()))


def _trim_incomplete_tail(text: str) -> str:
    cleaned = text.strip()
    if not cleaned or cleaned.endswith("…"):
        return cleaned
    if _ends_complete_sentence(cleaned):
        return cleaned
    if cleaned.count("«") > cleaned.count("»"):
        for match in reversed(list(re.finditer(r"\)\.\s+", cleaned))):
            end = match.start() + 2
            if end > len(cleaned) * 0.35:
                return cleaned[:end].strip() + "…"
        for match in reversed(list(re.finditer(r"\.\s+", cleaned))):
            end = match.start() + 1
            if end > len(cleaned) * 0.35:
                return cleaned[:end].strip() + "…"
        cut = cleaned.rfind("; ")
        if cut > len(cleaned) * 0.35:
            return cleaned[: cut + 1].rstrip() + "…"
    for match in reversed(list(re.finditer(r"[.!?](?:\s|$|»)", cleaned))):
        end = match.end()
        if end > len(cleaned) * 0.35:
            return cleaned[:end].strip() + "…"
    return cleaned + "…"


def _truncate_at_sentence_boundary(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    excerpt = text[: max_len - 1].rstrip()
    for match in reversed(list(re.finditer(r"[.!?;](?:\s|$|»)", excerpt))):
        end = match.end()
        if end > max_len * 0.5:
            return excerpt[:end].strip() + "…"
    return excerpt + "…"


def extract_relevant_excerpt(question: str, snippet: str, *, max_len: int = 1800) -> str:
    text = re.sub(r"\s+", " ", snippet).strip()
    lower = text.casefold()
    for phrase in significant_query_phrases(question):
        idx = lower.find(phrase)
        if idx >= 0:
            start = max(0, idx)
            remainder = text[start:]
            if len(remainder) <= max_len:
                excerpt = remainder
                suffix_ellipsis = False
            else:
                excerpt = remainder[:max_len].strip()
                suffix_ellipsis = True
            if start > 0:
                excerpt = "…" + excerpt
            if suffix_ellipsis:
                excerpt = _truncate_at_sentence_boundary(excerpt, max_len + 1)
            return _normalize_answer(excerpt)
    return _trim_snippet(question, snippet)


def _trim_snippet(question: str, snippet: str) -> str:
    text = re.sub(r"\s+", " ", snippet).strip()
    terms = [term for term in re.findall(r"[\w\u0400-\u04FF]+", question.casefold()) if len(term) >= 4]
    if not terms:
        return _normalize_answer(text)

    lower = text.casefold()
    best_idx = 0
    best_hits = -1
    window = 320
    for idx in range(0, max(1, len(text) - 40), 40):
        part = lower[idx : idx + window]
        hits = sum(1 for term in terms if term[:5] in part)
        if hits > best_hits:
            best_hits = hits
            best_idx = idx
    excerpt = text[best_idx : best_idx + window].strip()
    if best_idx > 0:
        excerpt = "…" + excerpt
    if best_idx + window < len(text):
        excerpt = excerpt + "…"
    return _normalize_answer(excerpt)


def generate_rule_based_answer(prompt: str) -> str:
    if "trigger_llm_down" in prompt:
        from app.core.errors import DependencyAppError

        raise DependencyAppError("LLM service is unavailable")

    question = extract_question_from_prompt(prompt)
    chunks = extract_context_chunks_from_prompt(prompt)
    if not chunks:
        return "Недостаточно данных в базе знаний по вашему вопросу."

    ranked = sorted(
        chunks,
        key=lambda item: (
            heading_match_score(question, item[1]),
            all_terms_match_score(question, item[1]),
            lexical_overlap_score(question, item[1]),
            1 if item[0].startswith("instructions.") else 0,
        ),
        reverse=True,
    )
    _, best_snippet = ranked[0]
    best_heading = heading_match_score(question, best_snippet)
    best_match = all_terms_match_score(question, best_snippet)
    best_lexical = lexical_overlap_score(question, best_snippet)

    if best_heading >= 0.85 or best_match >= 0.75 or best_lexical >= 0.5:
        return extract_relevant_excerpt(question, best_snippet)

    combined_context = "\n".join(snippet for _, snippet in chunks)
    faq_answer = extract_faq_answer(question, combined_context)
    if faq_answer:
        return faq_answer

    if best_lexical >= 0.25:
        return extract_relevant_excerpt(question, best_snippet)

    return "Недостаточно данных в базе знаний по вашему вопросу."
