from __future__ import annotations

import re

_RU_WORD = re.compile(r"[\w\u0400-\u04FF]+", re.UNICODE)
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
        "над",
        "под",
        "the",
        "and",
    }
)


def _query_terms(query: str) -> list[str]:
    terms = [_normalize_term(word) for word in _RU_WORD.findall(query.casefold())]
    return [term for term in terms if len(term) >= 3 and term not in _STOPWORDS]


def _normalize_term(word: str) -> str:
    return word.strip().casefold()


def _term_matches(term: str, text: str) -> bool:
    if term in text:
        return True
    if len(term) >= 5:
        stem = term[:5]
        if stem in text:
            return True
    return False


def lexical_overlap_score(query: str, text: str) -> float:
    terms = _query_terms(query)
    if not terms:
        return 0.0
    text_cf = text.casefold()
    hits = sum(1 for term in terms if _term_matches(term, text_cf))
    return min(1.0, hits / len(terms))


def all_terms_match_score(query: str, text: str) -> float:
    terms = _query_terms(query)
    if not terms:
        return 0.0
    text_cf = text.casefold()
    if all(_term_matches(term, text_cf) for term in terms):
        return 1.0
    return lexical_overlap_score(query, text)


def heading_match_score(question: str, text: str) -> float:
    question_cf = re.sub(r"\s+", " ", question.strip().casefold().rstrip("?")).strip()
    if not question_cf:
        return 0.0
    head = re.sub(r"\s+", " ", text.strip().casefold())[:180]
    if head.startswith(question_cf):
        return 1.0
    if question_cf in head:
        return 0.95
    terms = _query_terms(question)
    if terms and all(_term_matches(term, head) for term in terms):
        return 0.85
    return 0.0


def is_priority_instruction_chunk(query: str, doc_id: str, snippet: str) -> bool:
    if heading_match_score(query, snippet) >= 0.85:
        return True
    query_cf = query.casefold()
    if "восстанов" in query_cf and "доступ" in query_cf:
        return doc_id.endswith(("access_to_personal_account", "password"))
    if "пополн" in query_cf and "счет" in query_cf:
        return doc_id.endswith(".account")
    return False


def distinctive_terms(query: str) -> list[str]:
    return _query_terms(query)


def significant_query_phrases(query: str) -> list[str]:
    terms = _query_terms(query)
    phrases: list[str] = []
    for start in range(len(terms)):
        for end in range(start + 2, min(start + 7, len(terms) + 1)):
            phrase = " ".join(terms[start:end])
            if len(phrase) >= 8:
                phrases.append(phrase)
    return sorted(set(phrases), key=len, reverse=True)


def phrase_in_text_score(query: str, text: str) -> float:
    text_cf = text.casefold()
    best = 0.0
    for phrase in significant_query_phrases(query):
        if phrase in text_cf:
            best = max(best, min(1.0, len(phrase) / 36))
    if best:
        return best

    terms = _query_terms(query)
    if len(terms) < 3:
        return 0.0
    hits = 0
    cursor = 0
    for term in terms:
        idx = text_cf.find(term, cursor)
        if idx == -1 and len(term) >= 5:
            idx = text_cf.find(term[:5], cursor)
        if idx == -1:
            break
        hits += 1
        cursor = idx + max(1, len(term) - 2)
    if hits >= 3:
        return min(1.0, hits / len(terms) * 0.85)
    return 0.0
