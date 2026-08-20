"""BPM: task sequences per contract (specs/bpm.md)

Revision ID: 0036
Revises: 0035
Create Date: 2026-08-20

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0036"
down_revision: str | None = "0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_trigger = postgresql.ENUM(
    "contract_created", "status_reached", "manual", name="bpm_trigger", create_type=False
)
_kind = postgresql.ENUM(
    "user", "department", "role", name="bpm_assignee_kind", create_type=False
)
_status = postgresql.ENUM(
    "running", "done", "cancelled", name="bpm_instance_status", create_type=False
)
# Tipus que ja existeixen d'altres migracions: mai es tornen a crear.
_task_type = postgresql.ENUM(name="task_type", create_type=False)
_task_priority = postgresql.ENUM(name="task_priority", create_type=False)
_user_role = postgresql.ENUM(name="user_role", create_type=False)


def upgrade() -> None:
    for enum_type in (_trigger, _kind, _status):
        enum_type.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "bpm_workflows",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("trigger", _trigger, nullable=False),
        sa.Column("trigger_status", sa.String(255), nullable=True),
        sa.Column("active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "created_by",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_bpm_workflows_trigger", "bpm_workflows", ["trigger"])
    op.create_index("ix_bpm_workflows_active", "bpm_workflows", ["active"])

    op.create_table(
        "bpm_steps",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column(
            "workflow_id",
            sa.BigInteger(),
            sa.ForeignKey("bpm_workflows.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("task_type", _task_type, server_default="other", nullable=False),
        sa.Column("priority", _task_priority, server_default="normal", nullable=False),
        sa.Column("offset_days", sa.Integer(), server_default="0", nullable=False),
        sa.Column("assignee_kind", _kind, nullable=False),
        sa.Column(
            "assignee_user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "assignee_department_id",
            sa.BigInteger(),
            sa.ForeignKey("departments.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("assignee_role", _user_role, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("workflow_id", "position", name="uq_bpm_steps_position"),
    )
    op.create_index("ix_bpm_steps_workflow_id", "bpm_steps", ["workflow_id"])

    op.create_table(
        "bpm_instances",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column(
            "workflow_id",
            sa.BigInteger(),
            sa.ForeignKey("bpm_workflows.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "contract_id",
            sa.BigInteger(),
            sa.ForeignKey("contracts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", _status, server_default="running", nullable=False),
        sa.Column("current_position", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "current_task_id",
            sa.BigInteger(),
            sa.ForeignKey("tasks.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("workflow_id", "contract_id", name="uq_bpm_instances_contract"),
    )
    op.create_index("ix_bpm_instances_workflow_id", "bpm_instances", ["workflow_id"])
    op.create_index("ix_bpm_instances_contract_id", "bpm_instances", ["contract_id"])
    op.create_index("ix_bpm_instances_status", "bpm_instances", ["status"])

    for table in ("bpm_workflows", "bpm_steps", "bpm_instances"):
        op.execute(
            f"CREATE TRIGGER {table}_set_updated_at BEFORE UPDATE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
        )


def downgrade() -> None:
    op.drop_table("bpm_instances")
    op.drop_table("bpm_steps")
    op.drop_table("bpm_workflows")
    for name in ("bpm_instance_status", "bpm_assignee_kind", "bpm_trigger"):
        postgresql.ENUM(name=name).drop(op.get_bind(), checkfirst=True)
