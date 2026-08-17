"""Converses persistents del xat (specs/chat.md, B-016)."""

import enum
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Identity, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ChatScope(enum.StrEnum):
    GENERAL = "general"
    CONTRACT = "contract"


class ChatRole(enum.StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


_SCOPE = Enum(
    ChatScope,
    name="chat_scope",
    native_enum=False,
    length=20,
    values_callable=lambda e: [m.value for m in e],
)
_ROLE = Enum(
    ChatRole,
    name="chat_role",
    native_enum=False,
    length=20,
    values_callable=lambda e: [m.value for m in e],
)


class ChatThread(Base):
    __tablename__ = "chat_threads"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    scope: Mapped[ChatScope] = mapped_column(_SCOPE)
    contract_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("contracts.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    thread_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("chat_threads.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[ChatRole] = mapped_column(_ROLE)
    content: Mapped[str] = mapped_column(Text)
    sources: Mapped[list | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
