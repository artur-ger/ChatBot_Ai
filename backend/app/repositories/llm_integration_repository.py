from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.llm_integration import LlmIntegration


class LlmIntegrationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_all(self) -> list[LlmIntegration]:
        result = await self.session.execute(
            select(LlmIntegration).order_by(LlmIntegration.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_id(self, integration_id: str) -> LlmIntegration | None:
        result = await self.session.execute(
            select(LlmIntegration).where(LlmIntegration.id == integration_id)
        )
        return result.scalar_one_or_none()

    async def get_active(self) -> LlmIntegration | None:
        result = await self.session.execute(
            select(LlmIntegration).where(
                LlmIntegration.is_active.is_(True),
                LlmIntegration.enabled.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        name: str,
        provider: str,
        model: str,
        base_url: str | None,
        api_key_encrypted: str | None,
        enabled: bool,
        activate: bool,
    ) -> LlmIntegration:
        integration_id = uuid.uuid4().hex
        if activate:
            await self._deactivate_all()

        row = LlmIntegration(
            id=integration_id,
            name=name,
            provider=provider,
            model=model,
            base_url=base_url,
            api_key_encrypted=api_key_encrypted,
            enabled=enabled,
            is_active=activate,
        )
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def update(
        self,
        row: LlmIntegration,
        *,
        name: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        api_key_encrypted: str | None = None,
        enabled: bool | None = None,
        clear_api_key: bool = False,
    ) -> LlmIntegration:
        if name is not None:
            row.name = name
        if provider is not None:
            row.provider = provider
        if model is not None:
            row.model = model
        if base_url is not None:
            row.base_url = base_url
        if clear_api_key:
            row.api_key_encrypted = None
        elif api_key_encrypted is not None:
            row.api_key_encrypted = api_key_encrypted
        if enabled is not None:
            row.enabled = enabled
            if not enabled and row.is_active:
                row.is_active = False
        row.updated_at = datetime.now(timezone.utc)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def delete(self, row: LlmIntegration) -> None:
        await self.session.delete(row)
        await self.session.commit()

    async def activate(self, integration_id: str) -> LlmIntegration | None:
        row = await self.get_by_id(integration_id)
        if row is None:
            return None
        if not row.enabled:
            row.enabled = True
        await self._deactivate_all()
        row.is_active = True
        row.updated_at = datetime.now(timezone.utc)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def _deactivate_all(self) -> None:
        await self.session.execute(update(LlmIntegration).values(is_active=False))
