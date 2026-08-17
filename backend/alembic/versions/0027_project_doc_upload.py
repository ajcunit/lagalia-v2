"""allow user-uploaded project documents (no source url)

Revision ID: 0027
Revises: 0026
Create Date: 2026-08-17

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("project_documents", "source_url", existing_type=sa.Text(), nullable=True)


def downgrade() -> None:
    op.alter_column("project_documents", "source_url", existing_type=sa.Text(), nullable=False)
