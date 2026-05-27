import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.admin_auth import require_admin_auth
from app.core.config import settings
from app.core.errors import AppError, DependencyAppError, ValidationAppError
from app.core.limiter import limiter
from app.db.session import get_db_session
from app.schemas.chat import ErrorResponse
from app.schemas.llm_integration import (
    LlmIntegrationCreateRequest,
    LlmIntegrationListResponse,
    LlmIntegrationResponse,
    LlmIntegrationTestResponse,
    LlmIntegrationUpdateRequest,
    LlmModelsLookupRequest,
    LlmModelsLookupResponse,
    LlmProvidersListResponse,
    LlmProviderSpecResponse,
)
from app.services.llm_models import list_provider_models
from app.services.llm_provider_registry import list_provider_specs
from app.core.secret_encryption import decrypt_secret
from app.repositories.llm_integration_repository import LlmIntegrationRepository
from app.services.llm_factory import LlmClientFactory
from app.services.llm_integration_service import LlmIntegrationService

llm_integrations_router = APIRouter(
    prefix="/admin/llm/integrations",
    tags=["admin-llm"],
    dependencies=[Depends(require_admin_auth)],
)
logger = logging.getLogger(__name__)


def _app_error_response(exc: AppError, status_code: int) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(
            error_code=exc.error_code,
            message=exc.message,
            retry_allowed=exc.retry_allowed,
        ).model_dump(),
    )


def _get_factory(request: Request) -> LlmClientFactory:
    factory = getattr(request.app.state, "llm_factory", None)
    if factory is None:
        raise RuntimeError("LLM factory is not initialized")
    return factory


@llm_integrations_router.get("", response_model=LlmIntegrationListResponse)
@limiter.limit(settings.rate_limit_default)
async def list_llm_integrations(
    request: Request,
    db_session: AsyncSession = Depends(get_db_session),
) -> LlmIntegrationListResponse:
    service = LlmIntegrationService(db_session)
    return await service.list_integrations()


@llm_integrations_router.post(
    "",
    status_code=201,
    response_model=LlmIntegrationResponse,
    responses={400: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
)
@limiter.limit(settings.rate_limit_default)
async def create_llm_integration(
    request: Request,
    body: LlmIntegrationCreateRequest,
    db_session: AsyncSession = Depends(get_db_session),
) -> LlmIntegrationResponse | JSONResponse:
    try:
        service = LlmIntegrationService(db_session)
        created = await service.create_integration(body)
        _get_factory(request).invalidate_cache()
        return created
    except ValidationAppError as exc:
        return _app_error_response(exc, 400)


@llm_integrations_router.get(
    "/{integration_id}",
    response_model=LlmIntegrationResponse,
    responses={404: {"model": ErrorResponse}},
)
@limiter.limit(settings.rate_limit_default)
async def get_llm_integration(
    request: Request,
    integration_id: str,
    db_session: AsyncSession = Depends(get_db_session),
) -> LlmIntegrationResponse | JSONResponse:
    service = LlmIntegrationService(db_session)
    row = await service.get_integration(integration_id)
    if row is None:
        return JSONResponse(
            status_code=404,
            content=ErrorResponse(
                error_code="not_found",
                message="LLM integration not found",
                retry_allowed=False,
            ).model_dump(),
        )
    return row


@llm_integrations_router.put(
    "/{integration_id}",
    response_model=LlmIntegrationResponse,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
@limiter.limit(settings.rate_limit_default)
async def update_llm_integration(
    request: Request,
    integration_id: str,
    body: LlmIntegrationUpdateRequest,
    db_session: AsyncSession = Depends(get_db_session),
) -> LlmIntegrationResponse | JSONResponse:
    try:
        service = LlmIntegrationService(db_session)
        updated = await service.update_integration(integration_id, body)
        if updated is None:
            return JSONResponse(
                status_code=404,
                content=ErrorResponse(
                    error_code="not_found",
                    message="LLM integration not found",
                    retry_allowed=False,
                ).model_dump(),
            )
        _get_factory(request).invalidate_cache()
        return updated
    except ValidationAppError as exc:
        return _app_error_response(exc, 400)


@llm_integrations_router.delete(
    "/{integration_id}",
    response_model=None,
    responses={404: {"model": ErrorResponse}},
)
@limiter.limit(settings.rate_limit_default)
async def delete_llm_integration(
    request: Request,
    integration_id: str,
    db_session: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    service = LlmIntegrationService(db_session)
    deleted = await service.delete_integration(integration_id)
    if not deleted:
        return JSONResponse(
            status_code=404,
            content=ErrorResponse(
                error_code="not_found",
                message="LLM integration not found",
                retry_allowed=False,
            ).model_dump(),
        )
    _get_factory(request).invalidate_cache()
    return JSONResponse(content={"status": "deleted", "integration_id": integration_id})


@llm_integrations_router.post(
    "/{integration_id}/activate",
    response_model=LlmIntegrationResponse,
    responses={404: {"model": ErrorResponse}},
)
@limiter.limit(settings.rate_limit_default)
async def activate_llm_integration(
    request: Request,
    integration_id: str,
    db_session: AsyncSession = Depends(get_db_session),
) -> LlmIntegrationResponse | JSONResponse:
    service = LlmIntegrationService(db_session)
    activated = await service.activate_integration(integration_id)
    if activated is None:
        return JSONResponse(
            status_code=404,
            content=ErrorResponse(
                error_code="not_found",
                message="LLM integration not found",
                retry_allowed=False,
            ).model_dump(),
        )
    _get_factory(request).invalidate_cache()
    return activated


@llm_integrations_router.post(
    "/{integration_id}/test",
    response_model=LlmIntegrationTestResponse,
    responses={404: {"model": ErrorResponse}},
)
@limiter.limit(settings.rate_limit_default)
async def test_llm_integration(
    request: Request,
    integration_id: str,
    db_session: AsyncSession = Depends(get_db_session),
) -> LlmIntegrationTestResponse | JSONResponse:
    service = LlmIntegrationService(db_session)
    row = await service.get_integration(integration_id)
    if row is None:
        return JSONResponse(
            status_code=404,
            content=ErrorResponse(
                error_code="not_found",
                message="LLM integration not found",
                retry_allowed=False,
            ).model_dump(),
        )
    return await service.test_integration(integration_id)


llm_tools_router = APIRouter(
    prefix="/admin/llm",
    tags=["admin-llm"],
    dependencies=[Depends(require_admin_auth)],
)


@llm_tools_router.get("/providers", response_model=LlmProvidersListResponse)
@limiter.limit(settings.rate_limit_default)
async def list_llm_providers(request: Request) -> LlmProvidersListResponse:
    items = [
        LlmProviderSpecResponse(
            id=spec.id,
            label=spec.label,
            requires_base_url=spec.requires_base_url,
            requires_api_key=spec.requires_api_key,
            api_key_optional=spec.api_key_optional,
            base_url_placeholder=spec.base_url_placeholder,
            api_key_placeholder=spec.api_key_placeholder,
            models_source=spec.models_source,
            description=spec.description,
        )
        for spec in list_provider_specs()
    ]
    return LlmProvidersListResponse(items=items)


@llm_tools_router.post(
    "/models/lookup",
    response_model=LlmModelsLookupResponse,
    responses={400: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
)
@limiter.limit(settings.rate_limit_default)
async def lookup_llm_models(
    request: Request,
    body: LlmModelsLookupRequest,
) -> LlmModelsLookupResponse | JSONResponse:
    try:
        models = await list_provider_models(
            provider=body.provider,
            api_key=body.api_key,
            base_url=str(body.base_url) if body.base_url is not None else None,
        )
        return LlmModelsLookupResponse(provider=body.provider, models=models)
    except ValidationAppError as exc:
        return _app_error_response(exc, 400)
    except DependencyAppError as exc:
        return _app_error_response(exc, 503)


@llm_tools_router.post(
    "/integrations/{integration_id}/models",
    response_model=LlmModelsLookupResponse,
    responses={404: {"model": ErrorResponse}, 400: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
)
@limiter.limit(settings.rate_limit_default)
async def list_llm_integration_models(
    request: Request,
    integration_id: str,
    db_session: AsyncSession = Depends(get_db_session),
) -> LlmModelsLookupResponse | JSONResponse:
    repository = LlmIntegrationRepository(db_session)
    row = await repository.get_by_id(integration_id)
    if row is None:
        return JSONResponse(
            status_code=404,
            content=ErrorResponse(
                error_code="not_found",
                message="LLM integration not found",
                retry_allowed=False,
            ).model_dump(),
        )
    api_key = decrypt_secret(row.api_key_encrypted) if row.api_key_encrypted else None
    try:
        models = await list_provider_models(
            provider=row.provider,
            api_key=api_key,
            base_url=row.base_url,
        )
        return LlmModelsLookupResponse(provider=row.provider, models=models)  # type: ignore[arg-type]
    except ValidationAppError as exc:
        return _app_error_response(exc, 400)
    except DependencyAppError as exc:
        return _app_error_response(exc, 503)
