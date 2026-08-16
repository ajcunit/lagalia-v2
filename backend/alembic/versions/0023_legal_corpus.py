"""legal norms corpus (BOE) with per-article chunks

Revision ID: 0023
Revises: 0022
Create Date: 2026-08-16

"""

from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

from alembic import op

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "legal_norms",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("boe_id", sa.String(50), nullable=False, unique=True),
        sa.Column("title", sa.String(1000)),
        sa.Column("rank", sa.String(100)),
        sa.Column("published_at", sa.Date()),
        sa.Column("consolidated_version", sa.String(30)),
        sa.Column("articles_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("indexed_at", sa.DateTime(timezone=True)),
        sa.Column("last_checked_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_table(
        "legal_chunks",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column(
            "norm_id",
            sa.BigInteger(),
            sa.ForeignKey("legal_norms.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("article_label", sa.String(120), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", Vector()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "norm_id", "article_label", "chunk_index", name="uq_legal_chunks_article"
        ),
    )


def downgrade() -> None:
    op.drop_table("legal_chunks")
    op.drop_table("legal_norms")
