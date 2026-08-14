"""compliance reviews (deterministic LCSP rules engine)

Revision ID: 0020
Revises: 0019
Create Date: 2026-08-15

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "compliance_reviews",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("subject_type", sa.String(30), nullable=False, index=True),
        sa.Column("subject_id", sa.BigInteger(), nullable=False),
        sa.Column("ai_run_id", sa.BigInteger(), sa.ForeignKey("ai_runs.id", ondelete="SET NULL")),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("findings", postgresql.JSONB(), nullable=False),
        sa.Column("created_by", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_compliance_reviews_subject", "compliance_reviews", ["subject_type", "subject_id"]
    )


def downgrade() -> None:
    op.drop_table("compliance_reviews")
