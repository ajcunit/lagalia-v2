"""users.ical_key: clau opaca revocable per al feed iCal

Revision ID: 0011
Revises: 0010
Create Date: 2026-08-13

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("ical_key", sa.String(length=64), nullable=True))
    op.create_unique_constraint("uq_users_ical_key", "users", ["ical_key"])


def downgrade() -> None:
    op.drop_constraint("uq_users_ical_key", "users", type_="unique")
    op.drop_column("users", "ical_key")
