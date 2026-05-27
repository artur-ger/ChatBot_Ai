from fastapi import APIRouter, Body, Depends, Request
from fastapi.responses import JSONResponse

from app.core.admin_auth import require_admin_auth
from app.core.config import settings
from app.core.errors import AppError, ValidationAppError
from app.core.limiter import limiter
from app.schemas.chat import ErrorResponse
from app.schemas.rag_prompt import RagPromptResponse, RagPromptUpdateRequest
from app.services.rag_prompt_defaults import (
    DEFAULT_RAG_SYSTEM_INSTRUCTION,
    RAG_SYSTEM_INSTRUCTION_MAX_LEN,
)
from app.services.rag_prompt_service import RagPromptService

router = APIRouter(
    prefix="/admin/rag/prompt",
    tags=["admin-rag-prompt"],
    dependencies=[Depends(require_admin_auth)],
)


def _get_service(request: Request) -> RagPromptService:
    service = getattr(request.app.state, "rag_prompt_service", None)
    if service is None:
        raise RuntimeError("RAG prompt service is not initialized")
    return service


def _app_error_response(exc: AppError, status_code: int) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(
            error_code=exc.error_code,
            message=exc.message,
            retry_allowed=exc.retry_allowed,
        ).model_dump(),
    )


def _to_response(*, system_instruction: str, updated_at: str) -> RagPromptResponse:
    return RagPromptResponse(
        system_instruction=system_instruction,
        default_system_instruction=DEFAULT_RAG_SYSTEM_INSTRUCTION,
        is_default=RagPromptService.is_default_instruction(system_instruction),
        updated_at=updated_at,
        max_length=RAG_SYSTEM_INSTRUCTION_MAX_LEN,
    )


@router.get("", response_model=RagPromptResponse)
@limiter.limit(settings.rate_limit_default)
async def get_rag_prompt(request: Request) -> RagPromptResponse:
    service = _get_service(request)
    instruction, updated_at = await service.get_settings_view()
    return _to_response(system_instruction=instruction, updated_at=updated_at)


@router.put("", response_model=RagPromptResponse)
@limiter.limit(settings.rate_limit_default)
async def update_rag_prompt(
    request: Request,
    body: RagPromptUpdateRequest = Body(...),
) -> RagPromptResponse | JSONResponse:
    service = _get_service(request)
    try:
        instruction, updated_at = await service.update_system_instruction(
            system_instruction=body.system_instruction
        )
    except ValidationAppError as exc:
        return _app_error_response(exc, 400)
    return _to_response(system_instruction=instruction, updated_at=updated_at)


@router.post("/reset", response_model=RagPromptResponse)
@limiter.limit(settings.rate_limit_default)
async def reset_rag_prompt(request: Request) -> RagPromptResponse:
    service = _get_service(request)
    instruction, updated_at = await service.reset_to_default()
    return _to_response(system_instruction=instruction, updated_at=updated_at)
