from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.repositories.llm_integration_repository import LlmIntegrationRepository

logger = logging.getLogger(__name__)

DEFAULT_RULE_BASED_NAME = "Rule-based (dev default)"


async def ensure_default_llm_integration(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """Create an active rule_based integration when DB is empty (first deploy)."""
    if not settings.llm_bootstrap_default:
        return
    if not settings.llm_allow_rule_based_fallback:
        return

    async with session_factory() as session:
        repository = LlmIntegrationRepository(session)
        existing = await repository.list_all()
        if existing:
            return

        row = await repository.create(
            name=DEFAULT_RULE_BASED_NAME,
            provider="rule_based",
            model=settings.llm_model,
            base_url=None,
            api_key_encrypted=None,
            enabled=True,
            activate=True,
        )
        logger.info("Bootstrapped default LLM integration id=%s provider=rule_based", row.id)
