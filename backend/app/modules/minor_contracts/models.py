"""Contractes menors (docs/04-model-de-dades.md §2)."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    Numeric,
    String,
    Table,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.core.models import TimestampMixin
from app.modules.contractors.models import Contractor
from app.modules.contracts.models import _INTERNAL_STATUS, InternalStatus
from app.modules.departments.models import Department

minor_contract_departments = Table(
    "minor_contract_departments",
    Base.metadata,
    Column(
        "minor_contract_id",
        BigInteger,
        ForeignKey("minor_contracts.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "department_id",
        BigInteger,
        ForeignKey("departments.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
)


class MinorContract(Base, TimestampMixin):
    __tablename__ = "minor_contracts"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    file_code: Mapped[str] = mapped_column(String(100), unique=True)
    contract_type: Mapped[str | None] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    contractor_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("contractors.id", ondelete="SET NULL"), index=True
    )
    award_amount: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    award_date: Mapped[date | None] = mapped_column(Date, index=True)
    fiscal_year: Mapped[int | None] = mapped_column(Integer, index=True)
    duration_years: Mapped[int | None] = mapped_column(Integer)
    duration_months: Mapped[int | None] = mapped_column(Integer)
    duration_days: Mapped[int | None] = mapped_column(Integer)
    settlement_type: Mapped[str | None] = mapped_column(String(100))
    settlement_date: Mapped[date | None] = mapped_column(Date)
    settlement_amount: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    internal_status: Mapped[InternalStatus] = mapped_column(
        _INTERNAL_STATUS, server_default="normal", index=True
    )
    raw_award: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    raw_settlement: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    departments: Mapped[list[Department]] = relationship(secondary=minor_contract_departments)
    contractor: Mapped[Contractor | None] = relationship()
