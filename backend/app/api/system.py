from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.config import settings
from app.core.limiter import limiter
from app.db.session import SessionLocal
from app.repositories.llm_integration_repository import LlmIntegrationRepository
from app.schemas.chat import ErrorResponse
from app.schemas.ingestion import KbIndexHealthResponse, SystemInfoResponse
from app.services.kb_index_health import get_kb_index_status

logger = logging.getLogger(__name__)

router = APIRouter(tags=["system"])


@router.get("/healthz")
@limiter.limit(settings.rate_limit_default)
async def healthz(request: Request) -> dict[str, str]:
    started = time.perf_counter()
    # No DB/Redis/HTTP checks: fast liveness probe only.
    _ = started
    return {"status": "ok"}


@router.get("/readyz")
@limiter.limit(settings.rate_limit_default)
async def readyz(request: Request) -> object:
    try:
        async with SessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return {"status": "ready"}
    except Exception:
        return JSONResponse(
            status_code=503,
            content=ErrorResponse(
                error_code="dependency_unavailable",
                message="Database is not ready",
                retry_allowed=True,
            ).model_dump(),
        )


@router.get("/system/ui-config")
@limiter.limit(settings.rate_limit_default)
async def ui_config(request: Request) -> dict[str, bool]:
    return {
        "show_admin_link": settings.public_show_admin_link,
        "chat_acl_required": not settings.chat_acl_disabled,
    }


@router.get("/system/info", response_model=SystemInfoResponse)
@limiter.limit(settings.rate_limit_default)
async def system_info(request: Request) -> SystemInfoResponse:
    chroma_mode = "http" if settings.chroma_host else "persistent"
    active_id: str | None = None
    active_provider: str | None = None
    active_model: str | None = None
    integrations_count = 0
    try:
        async with SessionLocal() as session:
            repository = LlmIntegrationRepository(session)
            rows = await repository.list_all()
            integrations_count = len(rows)
            active = await repository.get_active()
            if active is not None:
                active_id = active.id
                active_provider = active.provider
                active_model = active.model
    except Exception:
        logger.exception("Failed to load LLM integration info")

    llm_configured = active_id is not None or settings.llm_allow_rule_based_fallback
    llm_using_fallback = active_id is None and settings.llm_allow_rule_based_fallback

    kb_index = await get_kb_index_status()
    return SystemInfoResponse(
        app_name=settings.app_name,
        api_prefix=settings.api_prefix,
        embedding_model_name=settings.embedding_model_name,
        embedding_model_version=settings.embedding_model_version,
        use_fake_embeddings=settings.use_fake_embeddings,
        chroma_mode=chroma_mode,
        llm_configured=llm_configured,
        llm_using_fallback=llm_using_fallback,
        active_llm_integration_id=active_id,
        active_llm_provider=active_provider,
        active_llm_model=active_model,
        llm_integrations_count=integrations_count,
        kb_index_state=kb_index.state,
        kb_indexed_documents=kb_index.indexed_documents,
        kb_chroma_chunks=kb_index.chroma_chunks,
        kb_index_message=kb_index.message,
    )


@router.get("/system/kb-index", response_model=KbIndexHealthResponse)
@limiter.limit(settings.rate_limit_default)
async def kb_index_health(request: Request) -> KbIndexHealthResponse:
    status = await get_kb_index_status(force=True)
    return KbIndexHealthResponse(
        state=status.state,
        indexed_documents=status.indexed_documents,
        chroma_chunks=status.chroma_chunks,
        embedding_model_version=status.embedding_model_version,
        message=status.message,
    )
