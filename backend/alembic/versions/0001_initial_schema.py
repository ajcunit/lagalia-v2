"""Esquema inicial: departments, users, user_departments, refresh_tokens, audit_log

Revision ID: 0001
Revises:
Create Date: 2026-08-11

Spec: specs/database-migrations.md
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# La CI no executa ops/db-init: l'extensió es crea aquí de forma idempotent.
_EXTENSIONS = "CREATE EXTENSION IF NOT EXISTS citext"

# clock_timestamp() i no now(): dins una mateixa transacció now() és constant
# i updated_at no reflectiria el canvi.
_SET_UPDATED_AT = """
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $$
BEGIN
    NEW.updated_at = clock_timestamp();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql
"""

_AUDIT_BLOCK = """
CREATE OR REPLACE FUNCTION audit_log_block_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_log is append-only';
END;
$$ LANGUAGE plpgsql
"""


def _updated_at_trigger(table: str) -> str:
    return (
        f"CREATE TRIGGER trg_{table}_updated_at BEFORE UPDATE ON {table} "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )


def upgrade() -> None:
    op.execute(_EXTENSIONS)
    op.execute(_SET_UPDATED_AT)
    op.execute(_AUDIT_BLOCK)

    user_role = pg.ENUM(
        "admin", "procurement_manager", "dept_manager", "employee", name="user_role"
    )
    audit_actor_type = pg.ENUM("user", "agent", "system", name="audit_actor_type")
    user_role.create(op.get_bind())
    audit_actor_type.create(op.get_bind())

    op.create_table(
        "departments",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("gestiona_group_id", sa.String(100), nullable=True),
        sa.Column("gestiona_group_name", sa.String(255), nullable=True),
        sa.Column("gestiona_group_href", sa.String(500), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("code", name="uq_departments_code"),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("email", pg.CITEXT(), nullable=False),
        sa.Column(
            "role",
            pg.ENUM(name="user_role", create_type=False),
            nullable=False,
        ),
        sa.Column("active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=True),
        sa.Column("dni_encrypted", sa.LargeBinary(), nullable=True),
        sa.Column("can_audit", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("can_plan", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )

    op.create_table(
        "user_departments",
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE", name="fk_user_departments_user_id_users"),
            primary_key=True,
        ),
        sa.Column(
            "department_id",
            sa.BigInteger(),
            sa.ForeignKey(
                "departments.id",
                ondelete="CASCADE",
                name="fk_user_departments_department_id_departments",
            ),
            primary_key=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_user_departments_department_id", "user_departments", ["department_id"])

    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("token_hash", sa.String(128), nullable=False),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE", name="fk_refresh_tokens_user_id_users"),
            nullable=False,
        ),
        sa.Column("family_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_ip", pg.INET(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("token_hash", name="uq_refresh_tokens_token_hash"),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_index("ix_refresh_tokens_family_id", "refresh_tokens", ["family_id"])

    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column(
            "occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "actor_type",
            pg.ENUM(name="audit_actor_type", create_type=False),
            nullable=False,
        ),
        sa.Column("actor_id", sa.BigInteger(), nullable=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("resource_type", sa.String(100), nullable=True),
        sa.Column("resource_id", sa.String(100), nullable=True),
        sa.Column("ip", pg.INET(), nullable=True),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column("trace_id", sa.String(100), nullable=True),
        sa.Column("details", pg.JSONB(), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("prev_hash", sa.String(64), nullable=True),
        sa.Column("entry_hash", sa.String(64), nullable=True),
    )
    op.create_index("ix_audit_log_occurred_at", "audit_log", ["occurred_at"])
    op.create_index("ix_audit_log_actor_id", "audit_log", ["actor_id"])
    op.create_index("ix_audit_log_action", "audit_log", ["action"])

    for table in ("departments", "users", "refresh_tokens"):
        op.execute(_updated_at_trigger(table))

    # Append-only: cap UPDATE ni DELETE, ni tan sols del propietari de l'esquema.
    op.execute(
        "CREATE TRIGGER trg_audit_log_immutable BEFORE UPDATE OR DELETE ON audit_log "
        "FOR EACH ROW EXECUTE FUNCTION audit_log_block_mutation()"
    )


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_table("refresh_tokens")
    op.drop_table("user_departments")
    op.drop_table("users")
    op.drop_table("departments")
    op.execute("DROP TYPE IF EXISTS audit_actor_type")
    op.execute("DROP TYPE IF EXISTS user_role")
    op.execute("DROP FUNCTION IF EXISTS audit_log_block_mutation()")
    op.execute("DROP FUNCTION IF EXISTS set_updated_at()")
