from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.text_extract import ExtractedTextSegment


@dataclass(frozen=True)
class TextChunk:
    text: str
    chunk_index: int
    page_number: int | None
    word_count: int


def normalize_text(text: str, *, lowercase: bool = False) -> str:
    cleaned = text.replace("\r\n", "\n").replace("\r", "\n").replace("\f", "\n\n")
    cleaned = re.sub(r"[\x00-\x08\x0b\x0e-\x1f\x7f]", "", cleaned)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r" *\n *", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned.casefold() if lowercase else cleaned


def _paragraphs(text: str) -> list[str]:
    return [paragraph.strip() for paragraph in re.split(r"\n\s*\n", text) if paragraph.strip()]


def _words(text: str) -> list[str]:
    return re.findall(r"\S+", text)


def _join_words(words: list[str]) -> str:
    return " ".join(words).strip()


def chunk_segments(
    segments: list[ExtractedTextSegment],
    *,
    chunk_size_words: int,
    overlap_words: int,
    min_words: int,
    lowercase: bool = False,
) -> list[TextChunk]:
    if chunk_size_words <= 0:
        raise ValueError("chunk_size_words must be positive")
    if min_words < 0:
        raise ValueError("min_words must be non-negative")

    safe_overlap = max(0, min(overlap_words, chunk_size_words // 2))
    chunks: list[TextChunk] = []
    buffer_words: list[str] = []
    buffer_page_number: int | None = None
    has_new_words = False

    def emit_buffer() -> None:
        nonlocal buffer_words, buffer_page_number, has_new_words
        if has_new_words and len(buffer_words) >= min_words:
            chunk_text_value = _join_words(buffer_words)
            chunks.append(
                TextChunk(
                    text=chunk_text_value,
                    chunk_index=len(chunks),
                    page_number=buffer_page_number,
                    word_count=len(buffer_words),
                )
            )
        tail = buffer_words[-safe_overlap:] if safe_overlap else []
        buffer_words = tail.copy()
        has_new_words = False

    for segment in segments:
        normalized = normalize_text(segment.text, lowercase=lowercase)
        for paragraph in _paragraphs(normalized):
            paragraph_words = _words(paragraph)
            if not paragraph_words:
                continue

            while paragraph_words:
                if not has_new_words:
                    buffer_page_number = segment.page_number

                capacity = chunk_size_words - len(buffer_words)
                if capacity <= 0:
                    emit_buffer()
                    continue

                portion = paragraph_words[:capacity]
                buffer_words.extend(portion)
                has_new_words = True
                paragraph_words = paragraph_words[capacity:]

                if len(buffer_words) >= chunk_size_words:
                    emit_buffer()

    if has_new_words and len(buffer_words) >= min_words:
        chunks.append(
            TextChunk(
                text=_join_words(buffer_words),
                chunk_index=len(chunks),
                page_number=buffer_page_number,
                word_count=len(buffer_words),
            )
        )

    deduped: list[TextChunk] = []
    seen: set[str] = set()
    for chunk in chunks:
        if chunk.text in seen:
            continue
        seen.add(chunk.text)
        deduped.append(
            TextChunk(
                text=chunk.text,
                chunk_index=len(deduped),
                page_number=chunk.page_number,
                word_count=chunk.word_count,
            )
        )
    return deduped


def chunk_text(text: str, *, chunk_size: int, overlap: int) -> list[str]:
    segments = [ExtractedTextSegment(text=text)]
    chunks = chunk_segments(
        segments,
        chunk_size_words=chunk_size,
        overlap_words=overlap,
        min_words=1,
    )
    return [chunk.text for chunk in chunks]
