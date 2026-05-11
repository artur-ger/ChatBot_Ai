from __future__ import annotations

from pathlib import Path

import aiosqlite

from app.config import settings


class DocumentStore:
    def __init__(self) -> None:
        self.db_path = Path(settings.bot_storage_path)

    async def init(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS user_documents (
                    chat_id TEXT NOT NULL,
                    document_id TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (chat_id, document_id)
                )
                """
            )
            await db.commit()

    async def add_document(
        self,
        *,
        chat_id: str,
        document_id: str,
        filename: str,
        status: str = "pending",
    ) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO user_documents(chat_id, document_id, filename, status)
                VALUES (?, ?, ?, ?)
                """,
                (chat_id, document_id, filename, status),
            )
            await db.commit()

    async def update_status(self, *, chat_id: str, document_id: str, status: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                UPDATE user_documents
                SET status = ?
                WHERE chat_id = ? AND document_id = ?
                """,
                (status, chat_id, document_id),
            )
            await db.commit()

    async def list_documents(self, *, chat_id: str) -> list[dict[str, str]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT document_id, filename, status, created_at
                FROM user_documents
                WHERE chat_id = ?
                ORDER BY created_at DESC
                """,
                (chat_id,),
            )
            rows = await cursor.fetchall()

        return [dict(row) for row in rows]