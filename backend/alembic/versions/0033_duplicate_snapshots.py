"""snapshots at contractor duplicate resolution (specs/contractor-normalization.md)

L'històric de fusions/rebutjos desapareixia: el CASCADE del contractista
perdedor s'enduia el parell. Ara el parell sobreviu (FK SET NULL) amb una
instantània de cada costat presa en el moment de resoldre.

Revision ID: 0033
Revises: 0032
Create Date: 2026-08-18

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0033"
down_revision: str | None = "0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "contractor_duplicates",
        sa.Column("snapshot_1", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "contractor_duplicates",
        sa.Column("snapshot_2", postgresql.JSONB(), nullable=True),
    )
    op.alter_column("contractor_duplicates", "contractor_id_1", nullable=True)
    op.alter_column("contractor_duplicates", "contractor_id_2", nullable=True)
    for side in ("1", "2"):
        op.drop_constraint(
            f"fk_contractor_duplicates_contractor_id_{side}_contractors",
            "contractor_duplicates",
            type_="foreignkey",
        )
        op.create_foreign_key(
            f"fk_contractor_duplicates_contractor_id_{side}_contractors",
            "contractor_duplicates",
            "contractors",
            [f"contractor_id_{side}"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    for side in ("1", "2"):
        op.drop_constraint(
            f"fk_contractor_duplicates_contractor_id_{side}_contractors",
            "contractor_duplicates",
            type_="foreignkey",
        )
        op.create_foreign_key(
            f"fk_contractor_duplicates_contractor_id_{side}_contractors",
            "contractor_duplicates",
            "contractors",
            [f"contractor_id_{side}"],
            ["id"],
            ondelete="CASCADE",
        )
    op.execute(
        "DELETE FROM contractor_duplicates WHERE contractor_id_1 IS NULL OR contractor_id_2 IS NULL"
    )
    op.alter_column("contractor_duplicates", "contractor_id_1", nullable=False)
    op.alter_column("contractor_duplicates", "contractor_id_2", nullable=False)
    op.drop_column("contractor_duplicates", "snapshot_2")
    op.drop_column("contractor_duplicates", "snapshot_1")
