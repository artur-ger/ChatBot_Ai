import logging
import uuid

from fastapi import APIRouter, Depends, File, Form, Request, Response, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AppError
from app.core.limiter import limiter
from app.db.session import get_db_session
from app.models.document import Document
from app.models.indexing_task import IndexingTask
from app.models.webhook_subscription import WebhookSubscription
from app.repositories.ingestion_repository import IngestionRepository
from app.schemas.chat import ErrorResponse
from app.schemas.ingestion import DocumentStatusResponse, IngestAcceptedResponse
from app.services.ingestion_service import save_upload_to_temp
from app.workers.tasks_indexing import index_document

router = APIRouter(prefix="/documents", tags=["documents"])
logger = logging.getLogger(__name__)


@router.post(
    "",
    status_code=202,
    response_model=IngestAcceptedResponse,
    responses={400: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
)
@limiter.limit(settings.rate_limit_default)
async def upload_document(
    request: Request,
    response: Response,
    file: UploadFile = File(),
    callback_url: str | None = Form(default=None),
    webhook_secret: str | None = Form(default=None),
    db_session: AsyncSession = Depends(get_db_session),
) -> IngestAcceptedResponse | JSONResponse:
    try:
        raw_bytes = await file.read()
        doc_id, temp_path, safe_name, mime_type, size_bytes, sha256, doc_type = (
            await save_upload_to_temp(
                filename=file.filename or "upload.bin",
                declared_content_type=file.content_type,
                file_bytes=raw_bytes,
            )
        )

        task_id = uuid.uuid4().hex
        repository = IngestionRepository(db_session)

        document = Document(
            id=doc_id,
            original_filename=safe_name,
            mime_type=mime_type,
            size_bytes=size_bytes,
            sha256=sha256,
            doc_type=doc_type,
            status="pending",
            temp_path=temp_path,
            error_message=None,
            embedding_model_version=settings.embedding_model_version,
        )
        task = IndexingTask(id=task_id, document_id=doc_id, status="pending")

        await repository.create_document(document)
        await repository.create_task(task)

        if callback_url:
            await repository.create_webhook(
                WebhookSubscription(document_id=doc_id, url=callback_url, secret=webhook_secret)
            )

        await repository.commit()

        try:
            async_result = index_document.apply_async(args=[doc_id, task_id], task_id=task_id)
        except Exception as exc:
            logger.exception("Failed to enqueue Celery task: %s", str(exc))
            await repository.update_document_status(
                document_id=doc_id, status="failed", error_message=str(exc)
            )
            await repository.update_task_status(
                task_id=task_id, status="failed", error_message=str(exc)
            )
            return JSONResponse(
                status_code=503,
                content=ErrorResponse(
                    error_code="dependency_unavailable",
                    message="Failed to enqueue indexing task",
                    retry_allowed=True,
                ).model_dump(),
            )

        await repository.set_task_celery_id(task_id=task_id, celery_task_id=async_result.id)

        response.headers["Location"] = f"/api/v1/indexing-tasks/{task_id}"
        return IngestAcceptedResponse(task_id=task_id, document_id=doc_id, status="pending")
    except AppError as exc:
        logger.warning("Upload validation error: %s", exc.message)
        return JSONResponse(
            status_code=400,
            content=ErrorResponse(
                error_code=exc.error_code,
                message=exc.message,
                retry_allowed=exc.retry_allowed,
            ).model_dump(),
        )


@router.get(
    "/{document_id}",
    response_model=DocumentStatusResponse,
    responses={404: {"model": ErrorResponse}},
)
@limiter.limit(settings.rate_limit_default)
async def get_document_status(
    request: Request,
    document_id: str,
    db_session: AsyncSession = Depends(get_db_session),
) -> DocumentStatusResponse | JSONResponse:
    repository = IngestionRepository(db_session)
    document = await repository.get_document(document_id)
    if not document:
        return JSONResponse(
            status_code=404,
            content=ErrorResponse(
                error_code="not_found",
                message="Document not found",
                retry_allowed=False,
            ).model_dump(),
        )
    return DocumentStatusResponse(
        document_id=document.id,
        status=document.status,
        error_message=document.error_message,
    )
