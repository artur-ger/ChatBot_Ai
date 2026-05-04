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
    error_message: str | None = None
    celery_task_id: str | None = None


class DocumentStatusResponse(BaseModel):
    document_id: str
    status: str
    error_message: str | None = None


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
