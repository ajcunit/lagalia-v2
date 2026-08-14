"""ai provider profiles and runs accounting

Revision ID: 0016
Revises: 0015
Create Date: 2026-08-14

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ai_protocol = sa.Enum("openai_compatible", "claude", "gemini", name="ai_protocol")


def upgrade() -> None:
    op.create_table(
        "ai_provider_profiles",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("protocol", ai_protocol, nullable=False),
        sa.Column("base_url", sa.String(500), nullable=False),
        sa.Column("api_key_encrypted", sa.LargeBinary()),
        sa.Column("default_model", sa.String(200)),
        sa.Column("capabilities", postgresql.JSONB()),
        sa.Column("enabled", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("health_status", sa.String(50)),
        sa.Column("last_health_check", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_table(
        "ai_runs",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("task", sa.String(100), nullable=False, index=True),
        sa.Column("agent", sa.String(100)),
        sa.Column(
            "provider_profile_id",
            sa.BigInteger(),
            sa.ForeignKey("ai_provider_profiles.id", ondelete="SET NULL"),
        ),
        sa.Column("model", sa.String(200)),
        sa.Column("input_summary", sa.String(500)),
        sa.Column("input_tokens", sa.Integer()),
        sa.Column("output_tokens", sa.Integer()),
        sa.Column("latency_ms", sa.Integer()),
        sa.Column("status", sa.String(20), nullable=False, index=True),
        sa.Column("error_detail", sa.String(1000)),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("trace_id", sa.String(100)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            index=True,
        ),
    )


def downgrade() -> None:
    op.drop_table("ai_runs")
    op.drop_table("ai_provider_profiles")
    ai_protocol.drop(op.get_bind(), checkfirst=True)
