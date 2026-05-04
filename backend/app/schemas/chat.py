from pydantic import BaseModel, Field


class SourceItem(BaseModel):
    doc_id: str
    snippet: str
    doc_type: str | None = None
    document_date: str | None = None


class ChatRequest(BaseModel):
    text: str = Field(min_length=2, max_length=3000)
    chat_id: str = Field(min_length=1, max_length=128)


class ChatResponse(BaseModel):
    text: str
    sources: list[SourceItem]
    confidence: float = Field(ge=0.0, le=1.0)
    chat_id: str


class ErrorResponse(BaseModel):
    error_code: str
    message: str
    retry_allowed: bool
