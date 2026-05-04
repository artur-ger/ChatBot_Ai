from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.indexing_task import IndexingTask
from app.models.webhook_subscription import WebhookSubscription


class IngestionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_document(self, document: Document) -> None:
        self.session.add(document)

    async def create_task(self, task: IndexingTask) -> None:
        self.session.add(task)

    async def create_webhook(self, webhook: WebhookSubscription) -> None:
        self.session.add(webhook)

    async def commit(self) -> None:
        await self.session.commit()

    async def get_document(self, document_id: str) -> Document | None:
        result = await self.session.execute(select(Document).where(Document.id == document_id))
        return result.scalar_one_or_none()

    async def get_task(self, task_id: str) -> IndexingTask | None:
        result = await self.session.execute(select(IndexingTask).where(IndexingTask.id == task_id))
        return result.scalar_one_or_none()

    async def get_webhook_for_document(self, document_id: str) -> WebhookSubscription | None:
        result = await self.session.execute(
            select(WebhookSubscription).where(WebhookSubscription.document_id == document_id)
        )
        return result.scalar_one_or_none()

    async def find_document_by_sha256(self, sha256: str) -> Document | None:
        result = await self.session.execute(select(Document).where(Document.sha256 == sha256))
        return result.scalar_one_or_none()

    async def update_document_status(
        self,
        *,
        document_id: str,
        status: str,
        error_message: str | None = None,
    ) -> None:
        await self.session.execute(
            update(Document)
            .where(Document.id == document_id)
            .values(status=status, error_message=error_message)
        )
        await self.session.commit()

    async def update_task_status(
        self,
        *,
        task_id: str,
        status: str,
        error_message: str | None = None,
        celery_task_id: str | None = None,
    ) -> None:
        values: dict[str, object] = {"status": status, "error_message": error_message}
        if celery_task_id is not None:
            values["celery_task_id"] = celery_task_id
        await self.session.execute(
            update(IndexingTask).where(IndexingTask.id == task_id).values(**values)
        )
        await self.session.commit()

    async def set_task_celery_id(self, *, task_id: str, celery_task_id: str) -> None:
        """Record Celery message id without touching status (safe with task_always_eager)."""
        await self.session.execute(
            update(IndexingTask)
            .where(IndexingTask.id == task_id)
            .values(celery_task_id=celery_task_id)
        )
        await self.session.commit()
