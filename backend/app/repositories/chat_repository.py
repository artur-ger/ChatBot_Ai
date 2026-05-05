from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat_message import ChatMessage


@dataclass
class ChatRecord:
    chat_id: str
    question: str
    answer: str
    confidence: float
    sources: list[dict[str, str | None]] | None = None
    retrieval_scores: list[float] | None = None
    latency_ms: int | None = None
    llm_model: str | None = None
    embedding_model_version: str | None = None


class ChatRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def save(self, record: ChatRecord) -> None:
        message = ChatMessage(
            chat_id=record.chat_id,
            question=record.question,
            answer=record.answer,
            confidence=record.confidence,
            sources_json=record.sources,
            retrieval_scores_json=record.retrieval_scores,
            latency_ms=record.latency_ms,
            llm_model=record.llm_model,
            embedding_model_version=record.embedding_model_version,
        )
        self.session.add(message)
        await self.session.commit()

    async def list_recent_messages(self, chat_id: str, limit: int) -> list[ChatMessage]:
        stmt = (
            select(ChatMessage)
            .where(ChatMessage.chat_id == chat_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        rows = list(result.scalars().all())
        rows.reverse()
        return rows

    async def list_history_page(
        self,
        *,
        chat_id: str,
        limit: int,
        cursor_created_at: datetime | None,
        cursor_id: int | None,
    ) -> tuple[list[ChatMessage], str | None, int | None]:
        stmt = select(ChatMessage).where(ChatMessage.chat_id == chat_id)
        if cursor_created_at is not None and cursor_id is not None:
            stmt = stmt.where(
                or_(
                    ChatMessage.created_at < cursor_created_at,
                    (ChatMessage.created_at == cursor_created_at) & (ChatMessage.id < cursor_id),
                )
            )
        stmt = stmt.order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc()).limit(limit + 1)
        result = await self.session.execute(stmt)
        rows = list(result.scalars().all())
        has_next = len(rows) > limit
        if has_next:
            rows = rows[:limit]
        next_cursor_created_at: str | None = None
        next_cursor_id: int | None = None
        if has_next and rows:
            tail = rows[-1]
            next_cursor_created_at = tail.created_at.isoformat()
            next_cursor_id = tail.id
        return rows, next_cursor_created_at, next_cursor_id

    async def reset_chat(self, chat_id: str) -> int:
        result = await self.session.execute(delete(ChatMessage).where(ChatMessage.chat_id == chat_id))
        await self.session.commit()
        return result.rowcount or 0
