import enum
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, Enum, Identity, String, func
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class AuditActorType(enum.StrEnum):
    USER = "user"
    AGENT = "agent"
    SYSTEM = "system"


class AuditLogEntry(Base):
    """Registre d'auditoria append-only (docs/04-model-de-dades.md §9).

    Sense updated_at deliberadament: un trigger a la BD rebutja UPDATE i
    DELETE. actor_id no és FK: pot referir un agent o el sistema, i una
    entrada ha de sobreviure a l'eliminació de l'actor.
    """

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    actor_type: Mapped[AuditActorType] = mapped_column(
        Enum(
            AuditActorType,
            name="audit_actor_type",
            values_callable=lambda e: [m.value for m in e],
        )
    )
    actor_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    action: Mapped[str] = mapped_column(String(100), index=True)
    resource_type: Mapped[str | None] = mapped_column(String(100))
    resource_id: Mapped[str | None] = mapped_column(String(100))
    ip: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(String(500))
    trace_id: Mapped[str | None] = mapped_column(String(100))
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    success: Mapped[bool] = mapped_column(Boolean)

    # Cadena de hash per a immutabilitat verificable: entry_hash =
    # sha256(prev_hash || contingut). prev_hash NULL només a la primera entrada.
    prev_hash: Mapped[str | None] = mapped_column(String(64))
    entry_hash: Mapped[str | None] = mapped_column(String(64))
