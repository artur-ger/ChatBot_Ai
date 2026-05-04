from dataclasses import dataclass

from sqlalchemy import select
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
