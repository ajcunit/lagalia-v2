"""add native ollama protocol to ai_protocol enum

Revision ID: 0018
Revises: 0017
Create Date: 2026-08-14

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE ai_protocol ADD VALUE IF NOT EXISTS 'ollama'")


def downgrade() -> None:
    # Treure un valor d'un enum no és segur; es deixa (inofensiu).
    pass
