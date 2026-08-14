"""Plataforma d'IA — perfils de proveidor i comptabilitat (specs/ai-providers.md)."""

import enum
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
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.models import TimestampMixin


class AiProtocol(enum.StrEnum):
    OPENAI_COMPATIBLE = "openai_compatible"
    CLAUDE = "claude"
    GEMINI = "gemini"


class AiProviderProfile(Base, TimestampMixin):
    __tablename__ = "ai_provider_profiles"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    protocol: Mapped[AiProtocol] = mapped_column(
        Enum(AiProtocol, name="ai_protocol", values_callable=lambda e: [m.value for m in e])
    )
    base_url: Mapped[str] = mapped_column(String(500))
    api_key_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary)
    default_model: Mapped[str | None] = mapped_column(String(200))
    capabilities: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    enabled: Mapped[bool] = mapped_column(Boolean, server_default="false")
    health_status: Mapped[str | None] = mapped_column(String(50))
    last_health_check: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AiRun(Base):
    __tablename__ = "ai_runs"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    task: Mapped[str] = mapped_column(String(100), index=True)
    agent: Mapped[str | None] = mapped_column(String(100))
    provider_profile_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("ai_provider_profiles.id", ondelete="SET NULL")
    )
    model: Mapped[str | None] = mapped_column(String(200))
    input_summary: Mapped[str | None] = mapped_column(String(500))
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), index=True)
    error_detail: Mapped[str | None] = mapped_column(String(1000))
    user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )
    trace_id: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
