"""Adjudicataris normalitzats (docs/04-model-de-dades.md §2).

La v1 duplicava nom/NIF a cada contracte; la v2 normalitza aquí i
conserva raw_contractor_name al contracte per traçabilitat.
"""

import enum
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Identity,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.models import TimestampMixin


class Contractor(Base, TimestampMixin):
    __tablename__ = "contractors"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    canonical_name: Mapped[str] = mapped_column(String(500))
    tax_id: Mapped[str | None] = mapped_column(String(20), index=True)
    nationality: Mapped[str | None] = mapped_column(String(100))
    company_type: Mapped[str | None] = mapped_column(String(100))
    third_sector: Mapped[bool] = mapped_column(Boolean, server_default="false")
    phone: Mapped[str | None] = mapped_column(String(50))
    email: Mapped[str | None] = mapped_column(String(255))


class ContractorAlias(Base, TimestampMixin):
    """Noms alternatius detectats; s'apliquen a la ingesta."""

    __tablename__ = "contractor_aliases"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    alias: Mapped[str] = mapped_column(String(500), unique=True)
    contractor_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("contractors.id", ondelete="CASCADE"), index=True
    )


class ContractorDuplicateStatus(enum.StrEnum):
    PENDING = "pending"
    MERGED = "merged"
    REJECTED = "rejected"


class ContractorDuplicate(Base, TimestampMixin):
    """Parells amb el mateix tax_id i nom diferent; es regenera a cada sync."""

    __tablename__ = "contractor_duplicates"
    __table_args__ = (
        UniqueConstraint(
            "contractor_id_1", "contractor_id_2", name="uq_contractor_duplicates_pair"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    contractor_id_1: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("contractors.id", ondelete="CASCADE")
    )
    contractor_id_2: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("contractors.id", ondelete="CASCADE")
    )
    status: Mapped[ContractorDuplicateStatus] = mapped_column(
        Enum(
            ContractorDuplicateStatus,
            name="contractor_duplicate_status",
            values_callable=lambda e: [m.value for m in e],
        ),
        server_default="pending",
    )
    resolved_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
