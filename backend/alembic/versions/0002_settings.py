"""Taula settings (configuració clau/valor)

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-12

Spec: specs/initial-setup.md
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "settings",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("key", sa.String(100), nullable=False),
        sa.Column("value", pg.JSONB(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_secret", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "updated_by",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="SET NULL", name="fk_settings_updated_by_users"),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("key", name="uq_settings_key"),
    )
    op.execute(
        "CREATE TRIGGER trg_settings_updated_at BEFORE UPDATE ON settings "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )


def downgrade() -> None:
    op.drop_table("settings")
