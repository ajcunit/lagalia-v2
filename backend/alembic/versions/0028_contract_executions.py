"""execution-phase publications from dataset 8idu-wkjv

Revision ID: 0028
Revises: 0027
Create Date: 2026-08-18

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "0028"
down_revision: str | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE sync_kind ADD VALUE IF NOT EXISTS 'execution'")
    op.create_table(
        "contract_executions",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column(
            "contract_id",
            sa.BigInteger(),
            sa.ForeignKey("contracts.id", ondelete="SET NULL"),
            index=True,
        ),
        sa.Column("file_code", sa.String(100), nullable=False, index=True),
        sa.Column("lot", sa.String(50)),
        sa.Column("action_type", sa.String(200)),
        sa.Column("action_name", sa.Text()),
        sa.Column("date", sa.Date()),
        sa.Column("end_date", sa.Date()),
        sa.Column("amount", sa.Numeric(14, 2)),
        sa.Column("contractor_name", sa.String(500)),
        sa.Column("contractor_tax_id", sa.String(50)),
        sa.Column("observations", sa.Text()),
        sa.Column("url_json", sa.Text()),
        sa.Column("raw", JSONB(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False, unique=True),
        sa.Column(
            "first_synced_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "last_synced_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("contract_executions")
    # El valor de l'enum no s'elimina (PostgreSQL no ho permet fàcilment).
