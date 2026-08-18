"""execution as a first-class document phase

Revision ID: 0030
Revises: 0029
Create Date: 2026-08-18

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0030"
down_revision: str | None = "0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE contract_phase ADD VALUE IF NOT EXISTS 'execucio'")


def downgrade() -> None:
    pass  # els valors d'enum no s'eliminen a PostgreSQL
