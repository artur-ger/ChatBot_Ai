import logging
import time
from datetime import datetime
from typing import cast

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.chat_acl import verify_chat_access
from app.core.config import settings
from app.core.errors import AppError
from app.core.limiter import limiter
from app.db.session import get_db_session
from app.repositories.chat_repository import ChatRecord, ChatRepository
from app.schemas.chat import (
    ChatHistoryItem,
    ChatHistoryResponse,
    ChatRequest,
    ChatResetResponse,
    ChatResponse,
    ErrorResponse,
)
from app.services.llm_factory import LlmClientFactory, LlmNotConfiguredError
from app.services.rag_pipeline import RagPipeline

router = APIRouter(prefix="/chat", tags=["chat"])
logger = logging.getLogger(__name__)


def get_pipeline(request: Request) -> RagPipeline:
    return cast(RagPipeline, request.app.state.rag_pipeline)


def get_llm_factory(request: Request) -> LlmClientFactory:
    return cast(LlmClientFactory, request.app.state.llm_factory)


@router.post(
    "",
    response_model=ChatResponse,
    responses={400: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
)
@limiter.limit(settings.rate_limit_chat)
async def chat(
    request: Request,
    payload: ChatRequest,
    x_chat_signature: str | None = Header(default=None, alias="X-Chat-Signature"),
    pipeline: RagPipeline = Depends(get_pipeline),
    llm_factory: LlmClientFactory = Depends(get_llm_factory),
    db_session: AsyncSession = Depends(get_db_session),
) -> ChatResponse | JSONResponse:
    try:
        if not settings.chat_acl_disabled:
            verify_chat_access(chat_id=payload.chat_id, provided_signature=x_chat_signature)
        llm_context = await llm_factory.get_active_context()
        repository = ChatRepository(db_session)
        history_rows = await repository.list_recent_messages(
            payload.chat_id,
            limit=settings.chat_history_max_messages,
        )
        history: list[tuple[str, str]] = []
        for row in history_rows:
            history.append(("user", row.question))
            history.append(("assistant", row.answer))

        start = time.perf_counter()
        response, retrieval_scores = await pipeline.answer(
            payload.text,
            payload.chat_id,
            history=history,
        )
        latency_ms = int((time.perf_counter() - start) * 1000)

        sources_payload = [source.model_dump() for source in response.sources]
        await repository.save(
            ChatRecord(
                chat_id=payload.chat_id,
                question=payload.text,
                answer=response.text,
                confidence=response.confidence,
                sources=sources_payload,
                retrieval_scores=retrieval_scores or None,
                latency_ms=latency_ms,
                llm_model=settings.llm_model,
                embedding_model_version=settings.embedding_model_version,
            )
        )
        return response
    except LlmNotConfiguredError as exc:
        return JSONResponse(
            status_code=503,
            content=ErrorResponse(
                error_code=exc.error_code,
                message=exc.message,
                retry_allowed=exc.retry_allowed,
            ).model_dump(),
        )
    except AppError as exc:
        logger.warning("Application error: %s", exc.message)
        status_code = 400 if exc.error_code == "validation_error" else 503
        return JSONResponse(
            status_code=status_code,
            content=ErrorResponse(
                error_code=exc.error_code,
                message=exc.message,
                retry_allowed=exc.retry_allowed,
            ).model_dump(),
        )


@router.get(
    "/{chat_id}/history",
    response_model=ChatHistoryResponse,
    responses={400: {"model": ErrorResponse}},
)
@limiter.limit(settings.rate_limit_default)
async def chat_history(
    request: Request,
    chat_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None),
    db_session: AsyncSession = Depends(get_db_session),
) -> ChatHistoryResponse | JSONResponse:
    cursor_created_at: datetime | None = None
    cursor_id: int | None = None
    if cursor:
        try:
            created_at_raw, id_raw = cursor.rsplit("|", 1)
            cursor_created_at = datetime.fromisoformat(created_at_raw)
            cursor_id = int(id_raw)
        except Exception:
            return JSONResponse(
                status_code=400,
                content=ErrorResponse(
                    error_code="validation_error",
                    message="Invalid cursor format",
                    retry_allowed=False,
                ).model_dump(),
            )
    repository = ChatRepository(db_session)
    rows, next_created_at, next_id = await repository.list_history_page(
        chat_id=chat_id,
        limit=limit,
        cursor_created_at=cursor_created_at,
        cursor_id=cursor_id,
    )
    items = [
        ChatHistoryItem(
            id=row.id,
            question=row.question,
            answer=row.answer,
            confidence=row.confidence,
            created_at=row.created_at.isoformat(),
        )
        for row in rows
    ]
    next_cursor = f"{next_created_at}|{next_id}" if next_created_at and next_id is not None else None
    return ChatHistoryResponse(chat_id=chat_id, items=items, next_cursor=next_cursor)


@router.post(
    "/{chat_id}/reset",
    response_model=ChatResetResponse,
    responses={400: {"model": ErrorResponse}},
)
@limiter.limit(settings.rate_limit_default)
async def reset_chat(
    request: Request,
    chat_id: str,
    db_session: AsyncSession = Depends(get_db_session),
) -> ChatResetResponse:
    repository = ChatRepository(db_session)
    deleted_messages = await repository.reset_chat(chat_id)
    return ChatResetResponse(chat_id=chat_id, deleted_messages=deleted_messages)
