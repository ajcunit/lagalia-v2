"""alert dismissal columns

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-12

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("contracts", sa.Column("alert_dismissed_at", sa.DateTime(timezone=True)))
    op.add_column("contracts", sa.Column("alert_dismissed_end_date", sa.Date()))


def downgrade() -> None:
    op.drop_column("contracts", "alert_dismissed_end_date")
    op.drop_column("contracts", "alert_dismissed_at")
