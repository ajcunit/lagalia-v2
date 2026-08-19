"""audit_log append-only with a sanctioned retention gate (specs/data-retention.md)

L'auditoria continua sent append-only per a tothom; només la purga de
retenció pot esborrar, i només files caducades: el trigger exigeix la
marca de sessió `app.retention_purge = 'on'` (SET LOCAL dins de la
transacció del job) i que la fila tingui més de 30 dies (xarxa de
seguretat: ni la purga pot esborrar auditoria fresca).

Revision ID: 0034
Revises: 0033
Create Date: 2026-08-19

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0034"
down_revision: str | None = "0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_GATED = """
CREATE OR REPLACE FUNCTION audit_log_block_mutation() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'DELETE'
       AND current_setting('app.retention_purge', true) = 'on'
       AND OLD.occurred_at < now() - interval '30 days' THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION 'audit_log is append-only';
END;
$$ LANGUAGE plpgsql
"""

_ORIGINAL = """
CREATE OR REPLACE FUNCTION audit_log_block_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_log is append-only';
END;
$$ LANGUAGE plpgsql
"""


def upgrade() -> None:
    op.execute(_GATED)


def downgrade() -> None:
    op.execute(_ORIGINAL)
