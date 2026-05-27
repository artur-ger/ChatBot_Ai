from __future__ import annotations

import pytest

from app.core.config import settings
from app.services.llm_bootstrap import DEFAULT_RULE_BASED_NAME, ensure_default_llm_integration


@pytest.mark.asyncio
async def test_bootstrap_creates_default_rule_based_integration(test_session):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    old_bootstrap = settings.llm_bootstrap_default
    old_fallback = settings.llm_allow_rule_based_fallback
    try:
        settings.llm_bootstrap_default = True
        settings.llm_allow_rule_based_fallback = True

        session_factory = async_sessionmaker(
            bind=test_session.bind,
            class_=type(test_session),
            expire_on_commit=False,
        )
        await ensure_default_llm_integration(session_factory)

        from app.repositories.llm_integration_repository import LlmIntegrationRepository

        repository = LlmIntegrationRepository(test_session)
        rows = await repository.list_all()
        assert len(rows) == 1
        assert rows[0].name == DEFAULT_RULE_BASED_NAME
        assert rows[0].provider == "rule_based"
        assert rows[0].is_active is True
    finally:
        settings.llm_bootstrap_default = old_bootstrap
        settings.llm_allow_rule_based_fallback = old_fallback


@pytest.mark.asyncio
async def test_bootstrap_skips_when_integrations_exist(test_session):
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.repositories.llm_integration_repository import LlmIntegrationRepository

    old_bootstrap = settings.llm_bootstrap_default
    try:
        repository = LlmIntegrationRepository(test_session)
        await repository.create(
            name="Existing",
            provider="rule_based",
            model="rule-based-llm",
            base_url=None,
            api_key_encrypted=None,
            enabled=True,
            activate=True,
        )

        session_factory = async_sessionmaker(
            bind=test_session.bind,
            class_=type(test_session),
            expire_on_commit=False,
        )
        settings.llm_bootstrap_default = True
        await ensure_default_llm_integration(session_factory)

        rows = await repository.list_all()
        assert len(rows) == 1
        assert rows[0].name == "Existing"
    finally:
        settings.llm_bootstrap_default = old_bootstrap
