"""manual field mapping overrides per data source

Revision ID: 0025
Revises: 0024
Create Date: 2026-08-17

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "field_mappings",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("target_field", sa.String(100), nullable=False),
        sa.Column("source_field", sa.String(80), nullable=False),
        sa.Column("updated_by", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("source", "target_field", name="uq_field_mappings_source_target"),
    )


def downgrade() -> None:
    op.drop_table("field_mappings")
