from __future__ import annotations

import logging
import uuid

from celery.result import AsyncResult
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.limiter import limiter
from app.db.session import get_db_session
from app.integrations.chroma_store import ChromaVectorStore
from app.models.indexing_task import IndexingTask
from app.repositories.ingestion_repository import IngestionRepository
from app.schemas.chat import ErrorResponse
from app.schemas.ingestion import IndexingTaskStatusResponse, TaskCancelResponse, TaskListResponse
from app.workers.celery_app import celery_app
from app.workers.tasks_indexing import index_document

router = APIRouter(prefix="/indexing-tasks", tags=["indexing"])
logger = logging.getLogger(__name__)


@router.get(
    "/{task_id}",
    response_model=IndexingTaskStatusResponse,
    responses={404: {"model": ErrorResponse}},
)
@limiter.limit(settings.rate_limit_default)
async def get_indexing_task_status(
    request: Request,
    task_id: str,
    db_session: AsyncSession = Depends(get_db_session),
) -> IndexingTaskStatusResponse | JSONResponse:
    repository = IngestionRepository(db_session)
    task = await repository.get_task(task_id)
    if not task:
        return JSONResponse(
            status_code=404,
            content=ErrorResponse(
                error_code="not_found",
                message="Task not found",
                retry_allowed=False,
            ).model_dump(),
        )

    return IndexingTaskStatusResponse(
        task_id=task.id,
        document_id=task.document_id,
        status=task.status,
        celery_status=AsyncResult(task.celery_task_id or task.id, app=celery_app).status,
        error_message=task.error_message,
        celery_task_id=task.celery_task_id,
    )


@router.get("", response_model=TaskListResponse)
@limiter.limit(settings.rate_limit_default)
async def list_indexing_tasks(
    request: Request,
    limit: int = Query(default=100, ge=1, le=500),
    db_session: AsyncSession = Depends(get_db_session),
) -> TaskListResponse:
    repository = IngestionRepository(db_session)
    tasks = await repository.list_indexing_tasks(limit=limit)
    items = [
        IndexingTaskStatusResponse(
            task_id=task.id,
            document_id=task.document_id,
            status=task.status,
            celery_status=AsyncResult(task.celery_task_id or task.id, app=celery_app).status,
            error_message=task.error_message,
            celery_task_id=task.celery_task_id,
        )
        for task in tasks
    ]
    return TaskListResponse(items=items)


@router.post(
    "/{task_id}/retry",
    response_model=IndexingTaskStatusResponse,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
@limiter.limit(settings.rate_limit_default)
async def retry_task(
    request: Request,
    task_id: str,
    db_session: AsyncSession = Depends(get_db_session),
) -> IndexingTaskStatusResponse | JSONResponse:
    repository = IngestionRepository(db_session)
    task = await repository.get_task(task_id)
    if task is None:
        return JSONResponse(
            status_code=404,
            content=ErrorResponse(error_code="not_found", message="Task not found", retry_allowed=False).model_dump(),
        )
    if task.status != "failed":
        return JSONResponse(
            status_code=400,
            content=ErrorResponse(
                error_code="validation_error",
                message="Only failed tasks can be retried",
                retry_allowed=False,
            ).model_dump(),
        )
    new_task_id = uuid.uuid4().hex
    await repository.create_task(
        IndexingTask(id=new_task_id, document_id=task.document_id, status="pending")
    )
    await repository.commit()
    async_result = index_document.apply_async(args=[task.document_id, new_task_id], task_id=new_task_id)
    await repository.set_task_celery_id(task_id=new_task_id, celery_task_id=async_result.id)
    return IndexingTaskStatusResponse(
        task_id=new_task_id,
        document_id=task.document_id,
        status="pending",
        celery_status=AsyncResult(async_result.id, app=celery_app).status,
        error_message=None,
        celery_task_id=async_result.id,
    )


@router.post(
    "/{task_id}/cancel",
    response_model=TaskCancelResponse,
    responses={404: {"model": ErrorResponse}},
)
@limiter.limit(settings.rate_limit_default)
async def cancel_task(
    request: Request,
    task_id: str,
    db_session: AsyncSession = Depends(get_db_session),
) -> TaskCancelResponse | JSONResponse:
    repository = IngestionRepository(db_session)
    task = await repository.get_task(task_id)
    if task is None:
        return JSONResponse(
            status_code=404,
            content=ErrorResponse(error_code="not_found", message="Task not found", retry_allowed=False).model_dump(),
        )
    if task.status in {"indexed", "cancelled"}:
        return JSONResponse(
            status_code=400,
            content=ErrorResponse(
                error_code="validation_error",
                message="Task cannot be cancelled in current state",
                retry_allowed=False,
            ).model_dump(),
        )
    document = await repository.get_document(task.document_id)
    if document is not None:
        vector_store = ChromaVectorStore(
            host=settings.chroma_host,
            port=settings.chroma_port,
            persist_path=settings.chroma_persist_path,
            collection_name=f"kb_{document.embedding_model_version}",
        )
        vector_store.delete_document_chunks(document.id)
    celery_id = task.celery_task_id or task.id
    celery_app.control.revoke(celery_id, terminate=True)
    await repository.update_task_status(task_id=task.id, status="cancelled", error_message="Cancelled by user")
    if document is not None:
        await repository.update_document_status(
            document_id=document.id,
            status="failed",
            error_message="Indexing cancelled by user",
        )
    return TaskCancelResponse(task_id=task.id, status="cancelled")
