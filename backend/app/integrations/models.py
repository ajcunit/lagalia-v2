"""Registre de sincronitzacions i de connectors (docs/04-model-de-dades.md §4 i §8)."""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Identity,
    Integer,
    LargeBinary,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.models import TimestampMixin

# La FK sync_runs.job_id → jobs.id exigeix que el mapper de Job estigui
# registrat allà on es toquen les sincronitzacions.
from app.jobs import models as _jobs_models  # noqa: F401  # isort: skip


class ConnectorMode(enum.StrEnum):
    NATIVE = "native"
    N8N_BRIDGE = "n8n_bridge"


class ConnectorRecord(Base, TimestampMixin):
    """Estat persistent d'un plugin del hub (docs/08-hub-integracions.md §1)."""

    __tablename__ = "connectors"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    slug: Mapped[str] = mapped_column(String(50), unique=True)
    enabled: Mapped[bool] = mapped_column(Boolean, server_default="false")
    mode: Mapped[ConnectorMode] = mapped_column(
        Enum(
            ConnectorMode,
            name="connector_mode",
            values_callable=lambda e: [m.value for m in e],
        ),
        server_default="native",
    )
    manifest: Mapped[dict[str, Any]] = mapped_column(JSONB)
    config: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    health_status: Mapped[str | None] = mapped_column(String(50))
    last_health_check: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ConnectorCredential(Base, TimestampMixin):
    """Credencial write-only, xifrada amb AES-256-GCM (core/crypto)."""

    __tablename__ = "connector_credentials"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    connector_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("connectors.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    value_encrypted: Mapped[bytes] = mapped_column(LargeBinary)
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SyncKind(enum.StrEnum):
    CONTRACTS = "contracts"
    MINOR = "minor"
    CPV = "cpv"
    EXTENSIONS = "extensions"
    ENRICHMENT = "enrichment"
    EXECUTION = "execution"


class SyncTrigger(enum.StrEnum):
    MANUAL = "manual"
    SCHEDULED = "scheduled"
    API = "api"


class SyncStatus(enum.StrEnum):
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL = "partial"


class SyncRun(Base, TimestampMixin):
    __tablename__ = "sync_runs"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    kind: Mapped[SyncKind] = mapped_column(
        Enum(SyncKind, name="sync_kind", values_callable=lambda e: [m.value for m in e]),
        index=True,
    )
    trigger: Mapped[SyncTrigger] = mapped_column(
        Enum(SyncTrigger, name="sync_trigger", values_callable=lambda e: [m.value for m in e])
    )
    # El job que l'executa: permet a l'escombrat veure que ha mort i tancar
    # l'execució, que si no es quedaria «executant» per sempre (B-021).
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="SET NULL"), index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[SyncStatus] = mapped_column(
        Enum(SyncStatus, name="sync_status", values_callable=lambda e: [m.value for m in e]),
        server_default="running",
        index=True,
    )
    new_count: Mapped[int] = mapped_column(Integer, server_default="0")
    updated_count: Mapped[int] = mapped_column(Integer, server_default="0")
    unchanged_count: Mapped[int] = mapped_column(Integer, server_default="0")
    total_source: Mapped[int | None] = mapped_column(Integer)
    endpoint: Mapped[str | None] = mapped_column(String(500))
    error_summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class SyncItemLog(Base, TimestampMixin):
    """Detall per registre problemàtic d'una sincronització."""

    __tablename__ = "sync_item_logs"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    sync_run_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sync_runs.id", ondelete="CASCADE"), index=True
    )
    file_code: Mapped[str | None] = mapped_column(String(100))
    outcome: Mapped[str | None] = mapped_column(String(100))
    message: Mapped[str | None] = mapped_column(String(1000))
