import logging
import time
from typing import cast

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.chat_acl import verify_chat_access
from app.core.config import settings
from app.core.errors import AppError
from app.core.limiter import limiter
from app.db.session import get_db_session
from app.repositories.chat_repository import ChatRecord, ChatRepository
from app.schemas.chat import ChatRequest, ChatResponse, ErrorResponse
from app.services.rag_pipeline import RagPipeline

router = APIRouter(prefix="/chat", tags=["chat"])
logger = logging.getLogger(__name__)


def get_pipeline(request: Request) -> RagPipeline:
    return cast(RagPipeline, request.app.state.rag_pipeline)


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
    db_session: AsyncSession = Depends(get_db_session),
) -> ChatResponse | JSONResponse:
    try:
        verify_chat_access(chat_id=payload.chat_id, provided_signature=x_chat_signature)
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
