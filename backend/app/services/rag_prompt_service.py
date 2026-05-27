from __future__ import annotations

import time

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.core.errors import ValidationAppError
from app.repositories.rag_prompt_repository import RagPromptRepository
from app.services.rag_prompt_defaults import (
    DEFAULT_RAG_SYSTEM_INSTRUCTION,
    RAG_SYSTEM_INSTRUCTION_MAX_LEN,
    RAG_SYSTEM_INSTRUCTION_MIN_LEN,
)


class RagPromptService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._cache: tuple[str, float] | None = None

    def invalidate_cache(self) -> None:
        self._cache = None

    @staticmethod
    def normalize_instruction(raw: str) -> str:
        normalized = raw.strip()
        if len(normalized) < RAG_SYSTEM_INSTRUCTION_MIN_LEN:
            raise ValidationAppError(
                f"System instruction must be at least {RAG_SYSTEM_INSTRUCTION_MIN_LEN} characters"
            )
        if len(normalized) > RAG_SYSTEM_INSTRUCTION_MAX_LEN:
            raise ValidationAppError(
                f"System instruction must be at most {RAG_SYSTEM_INSTRUCTION_MAX_LEN} characters"
            )
        return normalized

    async def get_system_instruction(self) -> str:
        now = time.time()
        if self._cache is not None:
            instruction, expires_at = self._cache
            if now < expires_at:
                return instruction
            self._cache = None

        async with self._session_factory() as session:
            repository = RagPromptRepository(session)
            row = await repository.get_or_create_default()
            instruction = row.system_instruction

        self._cache = (instruction, now + settings.rag_prompt_cache_ttl_sec)
        return instruction

    async def get_settings_view(self) -> tuple[str, str]:
        async with self._session_factory() as session:
            repository = RagPromptRepository(session)
            row = await repository.get_or_create_default()
            updated_at = row.updated_at.isoformat()
            return row.system_instruction, updated_at

    async def update_system_instruction(self, *, system_instruction: str) -> tuple[str, str]:
        normalized = self.normalize_instruction(system_instruction)
        async with self._session_factory() as session:
            repository = RagPromptRepository(session)
            row = await repository.update_system_instruction(system_instruction=normalized)
            updated_at = row.updated_at.isoformat()
        self.invalidate_cache()
        return normalized, updated_at

    async def reset_to_default(self) -> tuple[str, str]:
        return await self.update_system_instruction(system_instruction=DEFAULT_RAG_SYSTEM_INSTRUCTION)

    @staticmethod
    def is_default_instruction(instruction: str) -> bool:
        return instruction.strip() == DEFAULT_RAG_SYSTEM_INSTRUCTION.strip()
