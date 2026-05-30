from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ChatReply:
    text: str
    sources: list[dict[str, Any]]
    confidence: float


def parse_chat_reply(data: dict[str, Any]) -> ChatReply:
    return ChatReply(
        text=str(data.get("text") or "Не удалось получить текст ответа от сервиса."),
        sources=list(data.get("sources") or []),
        confidence=float(data.get("confidence") or 0.0),
    )


def format_sources_block(sources: list[dict[str, Any]], *, max_items: int = 3, snippet_len: int = 120) -> str:
    if not sources:
        return ""
    lines = ["\n\nИсточники:"]
    for source in sources[:max_items]:
        doc_id = str(source.get("doc_id") or "?")
        snippet = str(source.get("snippet") or "")
        if len(snippet) > snippet_len:
            snippet = snippet[: snippet_len - 1] + "…"
        lines.append(f"• [{doc_id}] {snippet}")
    return "\n".join(lines)


def format_chat_message(reply: ChatReply) -> str:
    return reply.text.strip()
