import logging
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.limiter import limiter
from app.schemas.chat import ErrorResponse
from app.schemas.ingestion import ReindexAcceptedResponse, ReindexRequest
from app.workers.tasks_indexing import reindex_documents

router = APIRouter(prefix="/admin", tags=["admin"])
logger = logging.getLogger(__name__)


@router.post(
    "/reindex",
    status_code=202,
    response_model=ReindexAcceptedResponse,
    responses={400: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
)
@limiter.limit(settings.rate_limit_default)
def enqueue_reindex(
    request: Request, payload: ReindexRequest
) -> ReindexAcceptedResponse | JSONResponse:
    try:
        task_id = uuid.uuid4().hex
        async_result = reindex_documents.apply_async(
            args=[payload.from_embedding_version, payload.to_embedding_version],
            task_id=task_id,
        )
        return ReindexAcceptedResponse(task_id=async_result.id)
    except Exception as exc:
        logger.exception("Failed to enqueue reindex: %s", str(exc))
        return JSONResponse(
            status_code=503,
            content=ErrorResponse(
                error_code="dependency_unavailable",
                message="Failed to enqueue reindex job",
                retry_allowed=True,
            ).model_dump(),
        )
