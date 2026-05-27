from __future__ import annotations

DEFAULT_RAG_SYSTEM_INSTRUCTION = (
    "Ты ассистент поддержки. Отвечай только по контексту. "
    "Если контекста недостаточно, сообщи об этом."
)

RAG_SYSTEM_INSTRUCTION_MIN_LEN = 10
RAG_SYSTEM_INSTRUCTION_MAX_LEN = 4000
