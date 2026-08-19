"""link sync runs to their job and close the orphaned ones (B-021)

Una execució tallada a mig fer (cancel·lació, temps exhaurit, worker
reiniciat) es quedava com a «executant» per sempre: `fail_run` només es
crida des d'un `except Exception` i `CancelledError` no ho és. Amb el
`job_id` desat, l'escombrat pot veure que el job ja és mort i tancar-la.

Les que hi ha ara no tenen el vincle: cap job viu les pot estar executant
(el desplegament recrea el worker), o sigui que es tanquen aquí.

Revision ID: 0035
Revises: 0034
Create Date: 2026-08-19

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0035"
down_revision: str | None = "0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "sync_runs",
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_sync_runs_job_id",
        "sync_runs",
        "jobs",
        ["job_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_sync_runs_job_id", "sync_runs", ["job_id"])

    op.execute(
        """
        UPDATE sync_runs
           SET status = 'failed',
               finished_at = now(),
               error_summary = jsonb_build_object(
                   'error',
                   'interrompuda: el treball es va aturar sense tancar '
                   'l''execucio (B-021)'
               )
         WHERE status = 'running'
        """
    )


def downgrade() -> None:
    op.drop_index("ix_sync_runs_job_id", table_name="sync_runs")
    op.drop_constraint("fk_sync_runs_job_id", "sync_runs", type_="foreignkey")
    op.drop_column("sync_runs", "job_id")
