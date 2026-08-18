"""Nucli de contractació (docs/04-model-de-dades.md §2).

Clau natural v1: UNIQUE(file_code, status, lot). Els noms catalans de la
font es mapegen al connector, mai aquí.
"""

import enum
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.core.models import TimestampMixin
from app.modules.contractors.models import Contractor
from app.modules.departments.models import Department
from app.modules.users.models import User

Amount = Numeric(15, 2)


class ContractSource(enum.StrEnum):
    LOCAL = "local"
    EXTERNAL = "external"


class InternalStatus(enum.StrEnum):
    NORMAL = "normal"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"


class ContractPhase(enum.StrEnum):
    FUTURA = "futura"
    AGREGADA = "agregada"
    CPM = "cpm"
    PREVI = "previ"
    LICITACIO = "licitacio"
    AVALUACIO = "avaluacio"
    ADJUDICACIO = "adjudicacio"
    FORMALITZACIO = "formalitzacio"
    ANULACIO = "anulacio"
    EXECUCIO = "execucio"  # documents de les actuacions d'execució (B-017)


class ChangeType(enum.StrEnum):
    SYNC = "sync"
    MANUAL = "manual"
    VALIDATION = "validation"
    GESTIONA_WEBHOOK = "gestiona_webhook"


_SOURCE = Enum(
    ContractSource, name="contract_source", values_callable=lambda e: [m.value for m in e]
)
_INTERNAL_STATUS = Enum(
    InternalStatus, name="internal_status", values_callable=lambda e: [m.value for m in e]
)
_PHASE = Enum(ContractPhase, name="contract_phase", values_callable=lambda e: [m.value for m in e])
_CHANGE_TYPE = Enum(ChangeType, name="change_type", values_callable=lambda e: [m.value for m in e])


contract_departments = Table(
    "contract_departments",
    Base.metadata,
    Column(
        "contract_id",
        BigInteger,
        ForeignKey("contracts.id", ondelete="CASCADE"),
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

contract_managers = Table(
    "contract_managers",
    Base.metadata,
    Column(
        "contract_id",
        BigInteger,
        ForeignKey("contracts.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("user_id", BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
)


class Contract(Base, TimestampMixin):
    __tablename__ = "contracts"
    __table_args__ = (
        UniqueConstraint("file_code", "status", "lot", name="uq_contracts_natural_key"),
        # Declarats aquí perquè l'autogenerate d'Alembic no els vegi com a orfes.
        Index("ix_contracts_raw_gin", "raw", postgresql_using="gin"),
        Index(
            "ix_contracts_subject_trgm",
            "subject",
            postgresql_using="gin",
            postgresql_ops={"subject": "gin_trgm_ops"},
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)

    # Identitat
    file_code: Mapped[str] = mapped_column(String(100), index=True)
    status: Mapped[str] = mapped_column(String(100), index=True)
    lot: Mapped[str] = mapped_column(String(50), server_default="")
    source: Mapped[ContractSource] = mapped_column(_SOURCE, server_default="external", index=True)
    gestiona_file_id: Mapped[str | None] = mapped_column(String(100))
    ine10_code: Mapped[str | None] = mapped_column(String(10))
    dir3_code: Mapped[str | None] = mapped_column(String(50))

    # Bàsics
    subject: Mapped[str | None] = mapped_column(Text)
    contract_type: Mapped[str | None] = mapped_column(String(100))
    procedure: Mapped[str | None] = mapped_column(String(100))
    processing_type: Mapped[str | None] = mapped_column(String(100))
    awarding_body: Mapped[str | None] = mapped_column(String(500))
    awarding_department: Mapped[str | None] = mapped_column(String(500), index=True)

    # Adjudicatari
    contractor_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("contractors.id", ondelete="SET NULL"), index=True
    )
    raw_contractor_name: Mapped[str | None] = mapped_column(String(500))

    # Imports
    tender_amount: Mapped[Decimal | None] = mapped_column(Amount)
    award_amount: Mapped[Decimal | None] = mapped_column(Amount)
    award_amount_vat: Mapped[Decimal | None] = mapped_column(Amount)
    estimated_value: Mapped[Decimal | None] = mapped_column(Amount)
    budget_no_vat: Mapped[Decimal | None] = mapped_column(Amount)
    budget_vat: Mapped[Decimal | None] = mapped_column(Amount)

    # Dates
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at_source: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    formalized_at: Mapped[date | None] = mapped_column(Date)
    start_date: Mapped[date | None] = mapped_column(Date, index=True)
    end_date: Mapped[date | None] = mapped_column(Date)
    calculated_end_date: Mapped[date | None] = mapped_column(Date, index=True)
    prior_notice_date: Mapped[date | None] = mapped_column(Date)
    tender_notice_date: Mapped[date | None] = mapped_column(Date)
    award_notice_date: Mapped[date | None] = mapped_column(Date)
    formalization_notice_date: Mapped[date | None] = mapped_column(Date)
    cancellation_date: Mapped[date | None] = mapped_column(Date)

    # Durada i alertes
    duration_months: Mapped[int | None] = mapped_column(Integer)
    expiry_warning: Mapped[bool] = mapped_column(Boolean, server_default="false")
    possibly_finished: Mapped[bool] = mapped_column(Boolean, server_default="false")
    warning_months_override: Mapped[int | None] = mapped_column(Integer)
    # Descart persistent: només val mentre calculated_end_date no canviï.
    alert_dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    alert_dismissed_end_date: Mapped[date | None] = mapped_column(Date)

    # Classificació. cpv_code fins a 255: la font de vegades hi concatena
    # diversos codis (verificat contra l'API real, sync_run 19).
    cpv_code: Mapped[str | None] = mapped_column(String(255), index=True)
    cpv_description: Mapped[str | None] = mapped_column(Text)
    nuts_code: Mapped[str | None] = mapped_column(String(10))
    nuts_description: Mapped[str | None] = mapped_column(String(255))
    financing: Mapped[str | None] = mapped_column(String(255))

    # Agrupacions JSONB (v1: 16 columnes disperses)
    links: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    phase_urls: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    enrichment: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    # Enriquiment promocionat (filtrable/mostrable en llistes)
    received_offers: Mapped[int | None] = mapped_column(Integer)
    is_harmonized: Mapped[bool | None] = mapped_column(Boolean)
    allows_extensions: Mapped[bool | None] = mapped_column(Boolean)
    allows_modifications: Mapped[bool | None] = mapped_column(Boolean)
    social_reserve: Mapped[bool | None] = mapped_column(Boolean)
    subcontracting_allowed: Mapped[bool | None] = mapped_column(Boolean)
    enriched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Control
    internal_status: Mapped[InternalStatus] = mapped_column(
        _INTERNAL_STATUS, server_default="normal", index=True
    )
    content_hash: Mapped[str | None] = mapped_column(String(64))
    raw: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    first_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    contractor: Mapped[Contractor | None] = relationship()
    departments: Mapped[list[Department]] = relationship(secondary=contract_departments)
    managers: Mapped[list[User]] = relationship(secondary=contract_managers)


class Extension(Base, TimestampMixin):
    """Pròrrogues."""

    __tablename__ = "extensions"
    __table_args__ = (UniqueConstraint("contract_id", "number", name="uq_extensions_contract_id"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    contract_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("contracts.id", ondelete="CASCADE"), index=True
    )
    number: Mapped[int] = mapped_column(Integer)
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    amount: Mapped[Decimal | None] = mapped_column(Amount)
    fiscal_year: Mapped[int | None] = mapped_column(Integer)
    raw: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class Modification(Base, TimestampMixin):
    __tablename__ = "modifications"
    __table_args__ = (
        UniqueConstraint("contract_id", "number", name="uq_modifications_contract_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    contract_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("contracts.id", ondelete="CASCADE"), index=True
    )
    number: Mapped[int] = mapped_column(Integer)
    approved_at: Mapped[date | None] = mapped_column(Date)
    type: Mapped[str | None] = mapped_column(String(100))
    amount: Mapped[Decimal | None] = mapped_column(Amount)
    term_years: Mapped[int | None] = mapped_column(Integer)
    term_months: Mapped[int | None] = mapped_column(Integer)
    term_days: Mapped[int | None] = mapped_column(Integer)
    raw: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class AwardCriterion(Base, TimestampMixin):
    __tablename__ = "award_criteria"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    contract_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("contracts.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(Text)
    weight: Mapped[Decimal | None] = mapped_column(Numeric(7, 2))
    breakdown: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class CommitteeMember(Base, TimestampMixin):
    __tablename__ = "committee_members"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    contract_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("contracts.id", ondelete="CASCADE"), index=True
    )
    first_name: Mapped[str | None] = mapped_column(String(255))
    last_name: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[str | None] = mapped_column(String(255))


class PhaseDocument(Base, TimestampMixin):
    __tablename__ = "phase_documents"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    contract_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("contracts.id", ondelete="CASCADE"), index=True
    )
    phase: Mapped[ContractPhase] = mapped_column(_PHASE)
    doc_type: Mapped[str | None] = mapped_column(String(100))
    title: Mapped[str | None] = mapped_column(Text)
    source_doc_id: Mapped[str | None] = mapped_column(String(200))
    source_hash: Mapped[str | None] = mapped_column(String(64))
    size: Mapped[int | None] = mapped_column(BigInteger)
    download_url: Mapped[str | None] = mapped_column(Text)
    storage_key: Mapped[str | None] = mapped_column(String(500))
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ContractHistoryEntry(Base):
    """Registre de canvis: no s'edita mai (sense updated_at)."""

    __tablename__ = "contract_history"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    contract_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("contracts.id", ondelete="CASCADE"), index=True
    )
    field: Mapped[str] = mapped_column(String(100))
    old_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)
    user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )
    change_type: Mapped[ChangeType] = mapped_column(_CHANGE_TYPE)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class DuplicateStatus(enum.StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    MERGED = "merged"


class ContractDuplicate(Base, TimestampMixin):
    """Parells de contractes duplicats; parell normalitzat (id1 < id2)."""

    __tablename__ = "duplicates"
    __table_args__ = (
        UniqueConstraint("contract_id_1", "contract_id_2", name="uq_duplicates_pair"),
        CheckConstraint("contract_id_1 < contract_id_2", name="pair_ordered"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    contract_id_1: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("contracts.id", ondelete="CASCADE")
    )
    contract_id_2: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("contracts.id", ondelete="CASCADE")
    )
    matched_on: Mapped[str | None] = mapped_column(String(255))
    reason: Mapped[str | None] = mapped_column(Text)
    status: Mapped[DuplicateStatus] = mapped_column(
        Enum(
            DuplicateStatus,
            name="duplicate_status",
            values_callable=lambda e: [m.value for m in e],
        ),
        server_default="pending",
        index=True,
    )
    action_taken: Mapped[str | None] = mapped_column(String(255))
    validated_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)


class RuleType(enum.StrEnum):
    DEPARTMENT = "department"
    BODY = "body"
    KEYWORD = "keyword"
    CPV = "cpv"
    AMOUNT = "amount"


class RuleOperator(enum.StrEnum):
    EQUALS = "equals"
    CONTAINS = "contains"
    STARTS_WITH = "starts_with"
    GT = "gt"
    LT = "lt"


class AssociationRule(Base, TimestampMixin):
    """Assignació automàtica de departaments; la v2 implementa TOTS els operadors."""

    __tablename__ = "association_rules"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    department_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("departments.id", ondelete="CASCADE"), index=True
    )
    rule_type: Mapped[RuleType] = mapped_column(
        Enum(RuleType, name="rule_type", values_callable=lambda e: [m.value for m in e])
    )
    source_field: Mapped[str] = mapped_column(String(100))
    match_value: Mapped[str] = mapped_column(String(500))
    operator: Mapped[RuleOperator] = mapped_column(
        Enum(RuleOperator, name="rule_operator", values_callable=lambda e: [m.value for m in e])
    )
    priority: Mapped[int] = mapped_column(Integer, server_default="100")
    active: Mapped[bool] = mapped_column(Boolean, server_default="true")


class CpvLevel(enum.StrEnum):
    DIVISION = "Division"
    GROUP = "Group"
    CLASS = "Class"
    CATEGORY = "Category"


class CpvCode(Base, TimestampMixin):
    __tablename__ = "cpv_codes"
    __table_args__ = (
        Index(
            "ix_cpv_codes_description_trgm",
            "description",
            postgresql_using="gin",
            postgresql_ops={"description": "gin_trgm_ops"},
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    description: Mapped[str] = mapped_column(Text)
    level: Mapped[CpvLevel | None] = mapped_column(
        Enum(CpvLevel, name="cpv_level", values_callable=lambda e: [m.value for m in e])
    )
    parent_code: Mapped[str | None] = mapped_column(String(20), index=True)
    raw: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
