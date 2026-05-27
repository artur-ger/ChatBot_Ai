import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, Query, Request, Response, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.admin_auth import require_admin_auth
from app.core.errors import AppError
from app.core.limiter import limiter
from app.db.session import get_db_session
from app.models.document import Document
from app.models.indexing_task import IndexingTask
from app.models.webhook_subscription import WebhookSubscription
from app.repositories.ingestion_repository import IngestionRepository
from app.schemas.chat import ErrorResponse
from app.schemas.ingestion import (
    DocumentListItem,
    DocumentListResponse,
    DocumentStatusResponse,
    IngestAcceptedResponse,
    KbArchiveDocumentAccepted,
    KbArchiveImportResponse,
)
from app.services.kb_archive_import import new_task_id, parse_kb_archive
from app.services.ingestion_service import save_upload_to_temp
from app.integrations.chroma_store import ChromaVectorStore
from app.workers.tasks_indexing import index_document

router = APIRouter(
    prefix="/documents",
    tags=["documents"],
    dependencies=[Depends(require_admin_auth)],
)
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


@router.post(
    "/kb-archive",
    status_code=202,
    response_model=KbArchiveImportResponse,
    responses={400: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
)
@limiter.limit(settings.rate_limit_default)
async def upload_kb_archive(
    request: Request,
    file: UploadFile = File(),
    db_session: AsyncSession = Depends(get_db_session),
) -> KbArchiveImportResponse | JSONResponse:
    try:
        raw_bytes = await file.read()
        entries = await parse_kb_archive(
            filename=file.filename or "kb.zip",
            declared_content_type=file.content_type,
            file_bytes=raw_bytes,
        )

        repository = IngestionRepository(db_session)
        vector_store = ChromaVectorStore(
            host=settings.chroma_host,
            port=settings.chroma_port,
            persist_path=settings.chroma_persist_path,
            collection_name=f"kb_{settings.embedding_model_version}",
        )

        accepted: list[tuple[str, str, str]] = []
        for entry in entries:
            existing = await repository.get_document(entry.document_id)
            if existing is not None:
                vector_store.delete_document_chunks(entry.document_id)
                await repository.delete_document(entry.document_id)

            task_id = new_task_id()
            await repository.create_document(
                Document(
                    id=entry.document_id,
                    original_filename=entry.original_filename,
                    mime_type="text/markdown" if entry.doc_type == "markdown" else "text/plain",
                    size_bytes=entry.size_bytes,
                    sha256=entry.sha256,
                    doc_type=entry.doc_type,
                    status="pending",
                    temp_path=entry.temp_path,
                    error_message=None,
                    embedding_model_version=settings.embedding_model_version,
                )
            )
            await repository.create_task(IndexingTask(id=task_id, document_id=entry.document_id, status="pending"))
            accepted.append((entry.document_id, task_id, entry.source_path))

        await repository.commit()

        for document_id, task_id, _source_path in accepted:
            try:
                async_result = index_document.apply_async(args=[document_id, task_id], task_id=task_id)
                await repository.set_task_celery_id(task_id=task_id, celery_task_id=async_result.id)
            except Exception as exc:
                logger.exception("Failed to enqueue KB indexing task: %s", str(exc))
                await repository.update_document_status(
                    document_id=document_id,
                    status="failed",
                    error_message=str(exc),
                )
                await repository.update_task_status(
                    task_id=task_id,
                    status="failed",
                    error_message=str(exc),
                )

        return KbArchiveImportResponse(
            accepted=len(accepted),
            skipped=len(entries) - len(accepted),
            items=[
                KbArchiveDocumentAccepted(
                    document_id=document_id,
                    task_id=task_id,
                    source_path=source_path,
                    status="pending",
                )
                for document_id, task_id, source_path in accepted
            ],
        )
    except AppError as exc:
        logger.warning("KB archive validation error: %s", exc.message)
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


@router.get(
    "",
    response_model=DocumentListResponse,
    responses={400: {"model": ErrorResponse}},
)
@limiter.limit(settings.rate_limit_default)
async def list_documents(
    request: Request,
    status: str | None = Query(default=None),
    doc_type: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None),
    db_session: AsyncSession = Depends(get_db_session),
) -> DocumentListResponse | JSONResponse:
    cursor_created_at: datetime | None = None
    cursor_id: str | None = None
    if cursor:
        try:
            created_at_raw, cursor_id = cursor.rsplit("|", 1)
            cursor_created_at = datetime.fromisoformat(created_at_raw)
        except Exception:
            return JSONResponse(
                status_code=400,
                content=ErrorResponse(
                    error_code="validation_error",
                    message="Invalid cursor format",
                    retry_allowed=False,
                ).model_dump(),
            )
    repository = IngestionRepository(db_session)
    docs, next_created_at, next_id = await repository.list_documents_page(
        status=status,
        doc_type=doc_type,
        limit=limit,
        cursor_created_at=cursor_created_at,
        cursor_id=cursor_id,
    )
    items = [
        DocumentListItem(
            document_id=doc.id,
            original_filename=doc.original_filename,
            doc_type=doc.doc_type,
            status=doc.status,
            created_at=doc.created_at.isoformat(),
            embedding_model_version=doc.embedding_model_version,
        )
        for doc in docs
    ]
    next_cursor = f"{next_created_at}|{next_id}" if next_created_at and next_id else None
    return DocumentListResponse(items=items, next_cursor=next_cursor)


@router.delete(
    "/{document_id}",
    responses={404: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
)
@limiter.limit(settings.rate_limit_default)
async def delete_document(
    request: Request,
    document_id: str,
    db_session: AsyncSession = Depends(get_db_session),
) -> object:
    repository = IngestionRepository(db_session)
    document = await repository.get_document(document_id)
    if document is None:
        return JSONResponse(
            status_code=404,
            content=ErrorResponse(
                error_code="not_found",
                message="Document not found",
                retry_allowed=False,
            ).model_dump(),
        )
    try:
        vector_store = ChromaVectorStore(
            host=settings.chroma_host,
            port=settings.chroma_port,
            persist_path=settings.chroma_persist_path,
            collection_name=f"kb_{document.embedding_model_version}",
        )
        vector_store.delete_document_chunks(document_id)
        await repository.delete_document(document_id)
        return Response(status_code=204)
    except Exception as exc:
        logger.exception("Failed to delete document atomically: %s", str(exc))
        return JSONResponse(
            status_code=503,
            content=ErrorResponse(
                error_code="dependency_unavailable",
                message="Failed to delete document",
                retry_allowed=True,
            ).model_dump(),
        )
