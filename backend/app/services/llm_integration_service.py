from __future__ import annotations

import time

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ValidationAppError
from app.core.secret_encryption import decrypt_secret, encrypt_secret, mask_api_key
from app.models.llm_integration import LlmIntegration
from app.repositories.llm_integration_repository import LlmIntegrationRepository
from app.schemas.llm_integration import (
    LlmIntegrationCreateRequest,
    LlmIntegrationListResponse,
    LlmIntegrationResponse,
    LlmIntegrationTestResponse,
    LlmIntegrationUpdateRequest,
)
from app.services.llm_provider_registry import get_provider_spec, validate_models_lookup_credentials
from app.services.llm_client import build_llm_client


def _to_response(row: LlmIntegration) -> LlmIntegrationResponse:
    masked: str | None = None
    if row.api_key_encrypted:
        try:
            masked = mask_api_key(decrypt_secret(row.api_key_encrypted))
        except ValidationAppError:
            masked = "***"
    return LlmIntegrationResponse(
        id=row.id,
        name=row.name,
        provider=row.provider,  # type: ignore[arg-type]
        model=row.model,
        base_url=row.base_url,
        api_key_masked=masked,
        is_active=row.is_active,
        enabled=row.enabled,
        created_at=row.created_at.isoformat(),
        updated_at=row.updated_at.isoformat(),
    )


def _validate_provider_fields(
    *,
    provider: str,
    base_url: str | None,
    api_key: str | None,
    require_key: bool,
) -> None:
    if provider == "rule_based":
        return
    if provider == "openai_compatible":
        if not base_url:
            raise ValidationAppError("base_url is required for openai_compatible provider")
        if require_key and not api_key:
            raise ValidationAppError("api_key is required for openai_compatible provider")
        return
    if provider == "gigachat":
        validate_models_lookup_credentials(provider=provider, api_key=api_key, base_url=base_url)
        return
    raise ValidationAppError(f"Unsupported provider: {provider}")


class LlmIntegrationService:
    def __init__(self, session: AsyncSession) -> None:
        self.repository = LlmIntegrationRepository(session)

    async def list_integrations(self) -> LlmIntegrationListResponse:
        rows = await self.repository.list_all()
        active_id = next((row.id for row in rows if row.is_active), None)
        return LlmIntegrationListResponse(
            items=[_to_response(row) for row in rows],
            active_integration_id=active_id,
        )

    async def get_integration(self, integration_id: str) -> LlmIntegrationResponse | None:
        row = await self.repository.get_by_id(integration_id)
        if row is None:
            return None
        return _to_response(row)

    async def create_integration(
        self, payload: LlmIntegrationCreateRequest
    ) -> LlmIntegrationResponse:
        base_url = str(payload.base_url) if payload.base_url is not None else None
        _validate_provider_fields(
            provider=payload.provider,
            base_url=base_url,
            api_key=payload.api_key,
            require_key=True,
        )
        encrypted_key = encrypt_secret(payload.api_key) if payload.api_key else None
        activate = payload.activate
        if activate:
            pass
        else:
            existing = await self.repository.list_all()
            if not existing:
                activate = True

        row = await self.repository.create(
            name=payload.name,
            provider=payload.provider,
            model=payload.model,
            base_url=base_url,
            api_key_encrypted=encrypted_key,
            enabled=payload.enabled,
            activate=activate,
        )
        return _to_response(row)

    async def update_integration(
        self, integration_id: str, payload: LlmIntegrationUpdateRequest
    ) -> LlmIntegrationResponse | None:
        row = await self.repository.get_by_id(integration_id)
        if row is None:
            return None

        provider = payload.provider or row.provider
        model = payload.model or row.model
        base_url = str(payload.base_url) if payload.base_url is not None else row.base_url
        api_key = payload.api_key
        if provider == "openai_compatible":
            if not base_url:
                raise ValidationAppError("base_url is required for openai_compatible provider")
            if api_key == "":
                raise ValidationAppError("api_key cannot be removed for openai_compatible provider")
            if api_key is None and not row.api_key_encrypted:
                raise ValidationAppError("api_key is required for openai_compatible provider")
        if provider == "gigachat":
            merged_key = api_key
            if merged_key is None and row.api_key_encrypted:
                merged_key = decrypt_secret(row.api_key_encrypted)
            if api_key == "":
                raise ValidationAppError("api_key нельзя удалить для gigachat — укажите новый ключ")
            validate_models_lookup_credentials(
                provider=provider,
                api_key=merged_key,
                base_url=base_url,
            )

        encrypted_key: str | None = None
        clear_api_key = False
        if api_key is not None:
            if api_key == "":
                clear_api_key = True
            else:
                encrypted_key = encrypt_secret(api_key)

        updated = await self.repository.update(
            row,
            name=payload.name,
            provider=payload.provider,
            model=payload.model,
            base_url=str(payload.base_url) if payload.base_url is not None else None,
            api_key_encrypted=encrypted_key,
            enabled=payload.enabled,
            clear_api_key=clear_api_key,
        )
        return _to_response(updated)

    async def delete_integration(self, integration_id: str) -> bool:
        row = await self.repository.get_by_id(integration_id)
        if row is None:
            return False
        await self.repository.delete(row)
        return True

    async def activate_integration(self, integration_id: str) -> LlmIntegrationResponse | None:
        row = await self.repository.activate(integration_id)
        if row is None:
            return None
        return _to_response(row)

    async def test_integration(self, integration_id: str) -> LlmIntegrationTestResponse:
        row = await self.repository.get_by_id(integration_id)
        if row is None:
            return LlmIntegrationTestResponse(
                integration_id=integration_id,
                ok=False,
                message="Integration not found",
            )

        api_key = decrypt_secret(row.api_key_encrypted) if row.api_key_encrypted else None
        try:
            client = build_llm_client(
                provider=row.provider,
                model=row.model,
                base_url=row.base_url,
                api_key=api_key,
            )
        except ValidationAppError as exc:
            return LlmIntegrationTestResponse(
                integration_id=integration_id,
                ok=False,
                message=exc.message,
            )

        started = time.perf_counter()
        try:
            text = await client.generate("Ответь одним словом: pong")
            latency_ms = int((time.perf_counter() - started) * 1000)
            preview = text[:120]
            return LlmIntegrationTestResponse(
                integration_id=integration_id,
                ok=True,
                message=f"LLM responded: {preview}",
                latency_ms=latency_ms,
            )
        except Exception as exc:
            latency_ms = int((time.perf_counter() - started) * 1000)
            return LlmIntegrationTestResponse(
                integration_id=integration_id,
                ok=False,
                message=str(exc),
                latency_ms=latency_ms,
            )
