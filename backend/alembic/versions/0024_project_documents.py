"""project-scoped temporary external reference documents

Revision ID: 0024
Revises: 0023
Create Date: 2026-08-17

"""

from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

from alembic import op

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "project_documents",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column(
            "project_id",
            sa.BigInteger(),
            sa.ForeignKey("doc_projects.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("file_code", sa.String(100)),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("storage_key", sa.String(500)),
        sa.Column("status", sa.String(20), server_default="pending", nullable=False),
        sa.Column("error_detail", sa.String(1000)),
        sa.Column("chunks_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("indexed_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_table(
        "project_chunks",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column(
            "project_id",
            sa.BigInteger(),
            sa.ForeignKey("doc_projects.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "project_document_id",
            sa.BigInteger(),
            sa.ForeignKey("project_documents.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", Vector()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("project_document_id", "chunk_index", name="uq_project_chunks_doc_idx"),
    )


def downgrade() -> None:
    op.drop_table("project_chunks")
    op.drop_table("project_documents")
