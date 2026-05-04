from __future__ import annotations

import re


def chunk_text(text: str, *, chunk_size: int, overlap: int) -> list[str]:
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        return []

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", cleaned) if p.strip()]
    chunks: list[str] = []
    buffer = ""

    for paragraph in paragraphs:
        candidate = (buffer + " " + paragraph).strip() if buffer else paragraph
        if len(candidate) <= chunk_size:
            buffer = candidate
            continue

        if buffer:
            chunks.extend(_split_with_overlap(buffer, chunk_size=chunk_size, overlap=overlap))
        chunks.extend(_split_with_overlap(paragraph, chunk_size=chunk_size, overlap=overlap))
        buffer = ""

    if buffer:
        chunks.extend(_split_with_overlap(buffer, chunk_size=chunk_size, overlap=overlap))

    deduped: list[str] = []
    seen: set[str] = set()
    for chunk in chunks:
        normalized = chunk.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


def _split_with_overlap(text: str, *, chunk_size: int, overlap: int) -> list[str]:
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]

    parts: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + chunk_size)
        parts.append(text[start:end].strip())
        if end == len(text):
            break
        start = max(0, end - overlap)
    return [part for part in parts if part]
