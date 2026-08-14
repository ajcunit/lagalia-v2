"""Pla anual de contractacio (specs/annual-plan.md; 04 §6)."""

import enum
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, Enum, ForeignKey, Identity, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.models import TimestampMixin


class PlanStatus(enum.StrEnum):
    PENDING = "pending"
    APPROVED = "approved"


class PlanEntry(Base, TimestampMixin):
    __tablename__ = "plan_entries"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    fiscal_year: Mapped[int] = mapped_column(Integer, index=True)
    quarter: Mapped[int] = mapped_column(Integer)
    subject: Mapped[str] = mapped_column(String(1000))
    contract_type: Mapped[str | None] = mapped_column(String(100))
    scope: Mapped[str | None] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(String(2000))
    subsidized: Mapped[bool] = mapped_column(Boolean, server_default="false")
    estimated_amount: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    status: Mapped[PlanStatus] = mapped_column(
        Enum(PlanStatus, name="plan_status", values_callable=lambda e: [m.value for m in e]),
        server_default="pending",
        index=True,
    )
    department_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("departments.id", ondelete="SET NULL")
    )
    contract_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("contracts.id", ondelete="SET NULL")
    )
    created_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )
