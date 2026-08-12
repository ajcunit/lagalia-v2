import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

# La FK created_by → users.id exigeix que el mapper d'User estigui
# registrat també als processos que només toquen jobs (worker, scheduler).
from app.modules.users import models as _users_models  # noqa: F401  # isort: skip

TERMINAL_STATUSES = frozenset({"success", "failed", "cancelled"})


class JobStatus(enum.StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        return self.value in TERMINAL_STATUSES


class Job(Base):
    """Registre durador d'un treball (docs/04-model-de-dades.md §4).

    L'id és el mateix que el job d'arq: traçabilitat 1:1 entre la cua
    i el registre. updated_at el manté el trigger de la BD.
    """

    __tablename__ = "jobs"
    __table_args__ = (
        Index(
            "uq_jobs_dedup_key_active",
            "dedup_key",
            unique=True,
            postgresql_where=text("dedup_key IS NOT NULL AND status IN ('queued', 'running')"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    type: Mapped[str] = mapped_column(String(100), index=True)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    status: Mapped[JobStatus] = mapped_column(
        Enum(
            JobStatus,
            name="job_status",
            values_callable=lambda e: [m.value for m in e],
        ),
        server_default="queued",
        index=True,
    )
    progress: Mapped[int] = mapped_column(Integer, server_default="0")
    progress_message: Mapped[str | None] = mapped_column(String(500))
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    dedup_key: Mapped[str | None] = mapped_column(String(200))
    attempts: Mapped[int] = mapped_column(Integer, server_default="0")
    created_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
