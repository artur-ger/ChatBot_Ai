from __future__ import annotations

from pydantic import BaseModel, Field


class IngestAcceptedResponse(BaseModel):
    task_id: str
    document_id: str
    status: str = Field(pattern="^(pending|processing|indexed|failed)$")


class IndexingTaskStatusResponse(BaseModel):
    task_id: str
    document_id: str
    status: str
    celery_status: str | None = None
    error_message: str | None = None
    celery_task_id: str | None = None


class DocumentStatusResponse(BaseModel):
    document_id: str
    status: str
    error_message: str | None = None


class DocumentListItem(BaseModel):
    document_id: str
    original_filename: str
    doc_type: str
    status: str
    created_at: str
    embedding_model_version: str


class DocumentListResponse(BaseModel):
    items: list[DocumentListItem]
    next_cursor: str | None = None


class WebhookCallbackPayload(BaseModel):
    document_id: str
    task_id: str
    status: str
    error: str | None = None


class ReindexRequest(BaseModel):
    from_embedding_version: str
    to_embedding_version: str


class ReindexAcceptedResponse(BaseModel):
    task_id: str


class TaskCancelResponse(BaseModel):
    task_id: str
    status: str


class TaskListResponse(BaseModel):
    items: list[IndexingTaskStatusResponse]


class SystemInfoResponse(BaseModel):
    app_name: str
    api_prefix: str
    embedding_model_name: str
    embedding_model_version: str
    use_fake_embeddings: bool
    chroma_mode: str
