"""favorites: personal folders with external snapshots

Revision ID: 0014
Revises: 0013
Create Date: 2026-08-14

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "favorite_folders",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.String(500)),
        sa.Column("color", sa.String(20)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_table(
        "favorites",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column(
            "folder_id",
            sa.BigInteger(),
            sa.ForeignKey("favorite_folders.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("file_code", sa.String(100), nullable=False),
        sa.Column("subject", sa.String(2000)),
        sa.Column("awarding_body", sa.String(500)),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("snapshot", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("folder_id", "file_code", name="uq_favorites_folder_code"),
    )


def downgrade() -> None:
    op.drop_table("favorites")
    op.drop_table("favorite_folders")
