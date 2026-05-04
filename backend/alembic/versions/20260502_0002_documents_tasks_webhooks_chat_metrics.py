"""documents, indexing tasks, webhooks, chat metrics

Revision ID: 20260502_0002
Revises: 20260502_0001
Create Date: 2026-05-02 03:05:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260502_0002"
down_revision: Union[str, Sequence[str], None] = "20260502_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("original_filename", sa.String(length=512), nullable=False),
        sa.Column("mime_type", sa.String(length=128), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("doc_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("temp_path", sa.Text(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("embedding_model_version", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_documents_sha256", "documents", ["sha256"], unique=False)
    op.create_index("ix_documents_status", "documents", ["status"], unique=False)

    op.create_table(
        "indexing_tasks",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("document_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("celery_task_id", sa.String(length=128), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_indexing_tasks_document_id", "indexing_tasks", ["document_id"], unique=False
    )
    op.create_index("ix_indexing_tasks_status", "indexing_tasks", ["status"], unique=False)

    op.create_table(
        "webhook_subscriptions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("document_id", sa.String(length=64), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("secret", sa.String(length=256), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_webhook_subscriptions_document_id",
        "webhook_subscriptions",
        ["document_id"],
        unique=False,
    )

    op.add_column("chat_messages", sa.Column("sources_json", sa.JSON(), nullable=True))
    op.add_column("chat_messages", sa.Column("retrieval_scores_json", sa.JSON(), nullable=True))
    op.add_column("chat_messages", sa.Column("latency_ms", sa.Integer(), nullable=True))
    op.add_column("chat_messages", sa.Column("llm_model", sa.String(length=128), nullable=True))
    op.add_column(
        "chat_messages",
        sa.Column("embedding_model_version", sa.String(length=128), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("chat_messages", "embedding_model_version")
    op.drop_column("chat_messages", "llm_model")
    op.drop_column("chat_messages", "latency_ms")
    op.drop_column("chat_messages", "retrieval_scores_json")
    op.drop_column("chat_messages", "sources_json")

    op.drop_index("ix_webhook_subscriptions_document_id", table_name="webhook_subscriptions")
    op.drop_table("webhook_subscriptions")

    op.drop_index("ix_indexing_tasks_status", table_name="indexing_tasks")
    op.drop_index("ix_indexing_tasks_document_id", table_name="indexing_tasks")
    op.drop_table("indexing_tasks")

    op.drop_index("ix_documents_status", table_name="documents")
    op.drop_index("ix_documents_sha256", table_name="documents")
    op.drop_table("documents")
