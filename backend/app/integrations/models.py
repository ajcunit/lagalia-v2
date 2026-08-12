"""Registre de sincronitzacions (docs/04-model-de-dades.md §4)."""

import enum
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Identity, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.models import TimestampMixin


class SyncKind(enum.StrEnum):
    CONTRACTS = "contracts"
    MINOR = "minor"
    CPV = "cpv"
    EXTENSIONS = "extensions"
    ENRICHMENT = "enrichment"


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
