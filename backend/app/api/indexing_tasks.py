from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.limiter import limiter
from app.db.session import get_db_session
from app.repositories.ingestion_repository import IngestionRepository
from app.schemas.chat import ErrorResponse
from app.schemas.ingestion import IndexingTaskStatusResponse

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
        error_message=task.error_message,
        celery_task_id=task.celery_task_id,
    )
