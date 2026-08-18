"""dead status for exhausted job retries (B-009)

Revision ID: 0031
Revises: 0030
Create Date: 2026-08-18

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0031"
down_revision: str | None = "0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE job_status ADD VALUE IF NOT EXISTS 'dead'")


def downgrade() -> None:
    pass  # els valors d'enum no s'eliminen a PostgreSQL
