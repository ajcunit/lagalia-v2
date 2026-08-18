"""ldap group mappings (specs/ldap-auth.md)

Revision ID: 0032
Revises: 0031
Create Date: 2026-08-18

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0032"
down_revision: str | None = "0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ldap_group_mappings",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("ad_group", sa.String(length=500), nullable=False),
        sa.Column(
            "role",
            postgresql.ENUM(name="user_role", create_type=False),
            nullable=True,
        ),
        sa.Column(
            "department_id",
            sa.BigInteger(),
            sa.ForeignKey("departments.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        # Cada regla és de rol O de departament, mai les dues coses ni cap.
        sa.CheckConstraint(
            "(role IS NULL) <> (department_id IS NULL)",
            name="ck_ldap_group_mappings_kind",
        ),
    )
    # Unicitat case-insensitive: els DN/CN d'AD no distingeixen majúscules.
    op.create_index(
        "uq_ldap_group_mappings_ad_group",
        "ldap_group_mappings",
        [sa.text("lower(ad_group)")],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("ldap_group_mappings")
