"""Taula jobs (cua de treballs)

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-12

Spec: specs/jobs-queue.md
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    job_status = pg.ENUM("queued", "running", "success", "failed", "cancelled", name="job_status")
    job_status.create(op.get_bind())

    op.create_table(
        "jobs",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("type", sa.String(100), nullable=False),
        sa.Column("payload", pg.JSONB(), nullable=True),
        sa.Column(
            "status",
            pg.ENUM(name="job_status", create_type=False),
            server_default="queued",
            nullable=False,
        ),
        sa.Column("progress", sa.Integer(), server_default="0", nullable=False),
        sa.Column("progress_message", sa.String(500), nullable=True),
        sa.Column("result", pg.JSONB(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("dedup_key", sa.String(200), nullable=True),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_by",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="SET NULL", name="fk_jobs_created_by_users"),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_jobs_type", "jobs", ["type"])
    op.create_index("ix_jobs_status", "jobs", ["status"])
    op.create_index("ix_jobs_created_by", "jobs", ["created_by"])
    # Una sola execució viva per dedup_key (p. ex. una única sync concurrent).
    op.create_index(
        "uq_jobs_dedup_key_active",
        "jobs",
        ["dedup_key"],
        unique=True,
        postgresql_where=sa.text("dedup_key IS NOT NULL AND status IN ('queued', 'running')"),
    )
    op.execute(
        "CREATE TRIGGER trg_jobs_updated_at BEFORE UPDATE ON jobs "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )


def downgrade() -> None:
    op.drop_table("jobs")
    op.execute("DROP TYPE IF EXISTS job_status")
