from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rag_prompt_setting import RAG_PROMPT_SETTING_ID, RagPromptSetting
from app.services.rag_prompt_defaults import DEFAULT_RAG_SYSTEM_INSTRUCTION


class RagPromptRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create_default(self) -> RagPromptSetting:
        row = (
            await self._session.execute(
                select(RagPromptSetting).where(RagPromptSetting.id == RAG_PROMPT_SETTING_ID)
            )
        ).scalar_one_or_none()
        if row is not None:
            return row

        row = RagPromptSetting(
            id=RAG_PROMPT_SETTING_ID,
            system_instruction=DEFAULT_RAG_SYSTEM_INSTRUCTION,
        )
        self._session.add(row)
        await self._session.commit()
        await self._session.refresh(row)
        return row

    async def update_system_instruction(self, *, system_instruction: str) -> RagPromptSetting:
        row = await self.get_or_create_default()
        row.system_instruction = system_instruction
        await self._session.commit()
        await self._session.refresh(row)
        return row
