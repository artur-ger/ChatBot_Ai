"""rag prompt settings singleton

Revision ID: 20260519_0004
Revises: 20260519_0003
Create Date: 2026-05-19 12:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260519_0004"
down_revision: Union[str, Sequence[str], None] = "20260519_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DEFAULT_INSTRUCTION = (
    "Ты ассистент поддержки. Отвечай только по контексту. "
    "Если контекста недостаточно, сообщи об этом."
)


def upgrade() -> None:
    op.create_table(
        "rag_prompt_settings",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("system_instruction", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute(
        sa.text(
            "INSERT INTO rag_prompt_settings (id, system_instruction) "
            "VALUES ('default', :instruction)"
        ).bindparams(instruction=DEFAULT_INSTRUCTION)
    )


def downgrade() -> None:
    op.drop_table("rag_prompt_settings")
