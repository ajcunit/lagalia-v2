"""annual procurement plan entries

Revision ID: 0015
Revises: 0014
Create Date: 2026-08-14

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

plan_status = sa.Enum("pending", "approved", name="plan_status")


def upgrade() -> None:
    op.create_table(
        "plan_entries",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("fiscal_year", sa.Integer(), nullable=False, index=True),
        sa.Column("quarter", sa.Integer(), nullable=False),
        sa.Column("subject", sa.String(1000), nullable=False),
        sa.Column("contract_type", sa.String(100)),
        sa.Column("scope", sa.String(200)),
        sa.Column("notes", sa.String(2000)),
        sa.Column("subsidized", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("estimated_amount", sa.Numeric(15, 2)),
        sa.Column("status", plan_status, server_default="pending", nullable=False, index=True),
        sa.Column(
            "department_id", sa.BigInteger(), sa.ForeignKey("departments.id", ondelete="SET NULL")
        ),
        sa.Column(
            "contract_id", sa.BigInteger(), sa.ForeignKey("contracts.id", ondelete="SET NULL")
        ),
        sa.Column("created_by", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_table("plan_entries")
    plan_status.drop(op.get_bind(), checkfirst=True)
