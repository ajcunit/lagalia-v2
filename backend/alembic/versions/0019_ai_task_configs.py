"""per-task ai provider/model configuration

Revision ID: 0019
Revises: 0018
Create Date: 2026-08-15

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_task_configs",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("task", sa.String(100), nullable=False, unique=True),
        sa.Column(
            "provider_profile_id",
            sa.BigInteger(),
            sa.ForeignKey("ai_provider_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("model", sa.String(200)),
        sa.Column("max_tokens", sa.Integer()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_table("ai_task_configs")
