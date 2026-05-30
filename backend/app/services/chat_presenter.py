from __future__ import annotations

import re

from app.schemas.chat import ChatResponse


def sanitize_user_answer_text(text: str) -> str:
    cleaned = text.strip()
    cleaned = re.split(r"\n+\s*Источники:\s*", cleaned, maxsplit=1, flags=re.IGNORECASE)[0]
    cleaned = re.split(r"\n+\s*Уверенность:\s*", cleaned, maxsplit=1, flags=re.IGNORECASE)[0]
    cleaned = re.sub(r"^[-•]\s*\[[\w.-]+\].*$", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"(?<!\w)\[[\w.-]+\](?:\s*,\s*\[[\w.-]+\])*", "", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def present_chat_response(response: ChatResponse) -> ChatResponse:
    return ChatResponse(
        text=sanitize_user_answer_text(response.text),
        sources=[],
        confidence=0.0,
        chat_id=response.chat_id,
    )
