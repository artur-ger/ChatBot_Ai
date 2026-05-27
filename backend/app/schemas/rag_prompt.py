from __future__ import annotations

from pydantic import BaseModel, Field

RAG_SYSTEM_INSTRUCTION_MAX_LEN = 4000

class RagPromptResponse(BaseModel):
    system_instruction: str
    default_system_instruction: str
    is_default: bool
    updated_at: str
    max_length: int


class RagPromptUpdateRequest(BaseModel):
    system_instruction: str = Field(min_length=1, max_length=RAG_SYSTEM_INSTRUCTION_MAX_LEN)
