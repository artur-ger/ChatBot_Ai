from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.core.errors import AppError, ValidationAppError
from app.core.secret_encryption import decrypt_secret
from app.models.llm_integration import LlmIntegration
from app.repositories.llm_integration_repository import LlmIntegrationRepository
from app.services.llm_client import BaseLlmClient, RuleBasedLlmClient, build_llm_client

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ActiveLlmContext:
    client: BaseLlmClient
    model_name: str
    integration_id: str | None
    provider: str


class LlmNotConfiguredError(AppError):
    def __init__(self) -> None:
        super().__init__(
            "llm_not_configured",
            "No active LLM integration is configured",
            retry_allowed=False,
        )


class LlmClientFactory:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._cache: tuple[str, ActiveLlmContext, float] | None = None

    def invalidate_cache(self) -> None:
        self._cache = None

    async def get_active_context(self) -> ActiveLlmContext:
        now = time.time()
        if self._cache is not None:
            integration_id, context, expires_at = self._cache
            if now < expires_at:
                return context
            self._cache = None

        async with self._session_factory() as session:
            repository = LlmIntegrationRepository(session)
            row = await repository.get_active()

        context = self._build_context(row)
        if row is not None:
            self._cache = (row.id, context, now + settings.llm_integration_cache_ttl_sec)
        return context

    def _build_context(self, row: LlmIntegration | None) -> ActiveLlmContext:
        if row is None:
            if settings.llm_allow_rule_based_fallback:
                return ActiveLlmContext(
                    client=RuleBasedLlmClient(),
                    model_name=settings.llm_model,
                    integration_id=None,
                    provider="rule_based",
                )
            raise LlmNotConfiguredError()

        api_key: str | None = None
        if row.api_key_encrypted:
            api_key = decrypt_secret(row.api_key_encrypted)

        try:
            client = build_llm_client(
                provider=row.provider,
                model=row.model,
                base_url=row.base_url,
                api_key=api_key,
            )
        except ValidationAppError:
            raise
        except Exception as exc:
            logger.exception("Failed to build LLM client for integration %s", row.id)
            raise ValidationAppError(f"Invalid LLM integration configuration: {exc}") from exc

        return ActiveLlmContext(
            client=client,
            model_name=row.model,
            integration_id=row.id,
            provider=row.provider,
        )
