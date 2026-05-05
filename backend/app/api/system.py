from __future__ import annotations

import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.config import settings
from app.core.limiter import limiter
from app.db.session import SessionLocal
from app.schemas.chat import ErrorResponse
from app.schemas.ingestion import SystemInfoResponse

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


@router.get("/system/info", response_model=SystemInfoResponse)
@limiter.limit(settings.rate_limit_default)
async def system_info(request: Request) -> SystemInfoResponse:
    chroma_mode = "http" if settings.chroma_host else "persistent"
    return SystemInfoResponse(
        app_name=settings.app_name,
        api_prefix=settings.api_prefix,
        embedding_model_name=settings.embedding_model_name,
        embedding_model_version=settings.embedding_model_version,
        use_fake_embeddings=settings.use_fake_embeddings,
        chroma_mode=chroma_mode,
    )
