"""execution detail enrichment: enabling assumption and documents

Revision ID: 0029
Revises: 0028
Create Date: 2026-08-18

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "0029"
down_revision: str | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("contract_executions", sa.Column("suposit_habilitant", sa.Text()))
    op.add_column("contract_executions", sa.Column("documents", JSONB()))
    op.add_column(
        "contract_executions", sa.Column("detail_fetched_at", sa.DateTime(timezone=True))
    )


def downgrade() -> None:
    op.drop_column("contract_executions", "detail_fetched_at")
    op.drop_column("contract_executions", "documents")
    op.drop_column("contract_executions", "suposit_habilitant")
