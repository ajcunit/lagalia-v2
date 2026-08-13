"""Tasques i recordatoris de contracte (docs/04-model-de-dades.md §4bis).

plan_entry_id s'afegirà amb el pla anual (desviació anotada a la spec).
"""

import enum
from datetime import date, datetime, time
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Identity,
    Integer,
    String,
    Table,
    Text,
    Time,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.core.models import TimestampMixin
from app.modules.users.models import User


class TaskType(enum.StrEnum):
    REVIEW = "review"
    EXTENSION = "extension"
    SETTLEMENT = "settlement"
    GUARANTEE_RETURN = "guarantee_return"
    REPORT = "report"
    MEETING = "meeting"
    OTHER = "other"


class TaskPriority(enum.StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


class TaskStatus(enum.StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    CANCELLED = "cancelled"

    @property
    def is_open(self) -> bool:
        return self in (TaskStatus.PENDING, TaskStatus.IN_PROGRESS)


class ReminderChannel(enum.StrEnum):
    EMAIL = "email"
    WEBHOOK = "webhook"


_TYPE = Enum(TaskType, name="task_type", values_callable=lambda e: [m.value for m in e])
_PRIORITY = Enum(TaskPriority, name="task_priority", values_callable=lambda e: [m.value for m in e])
_STATUS = Enum(TaskStatus, name="task_status", values_callable=lambda e: [m.value for m in e])
_CHANNEL = Enum(
    ReminderChannel, name="reminder_channel", values_callable=lambda e: [m.value for m in e]
)


task_assignees = Table(
    "task_assignees",
    Base.metadata,
    Column("task_id", BigInteger, ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True),
    Column("user_id", BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
)


class Task(Base, TimestampMixin):
    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint(
            "contract_id IS NOT NULL OR minor_contract_id IS NOT NULL",
            name="ck_tasks_has_subject",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    task_type: Mapped[TaskType] = mapped_column(_TYPE, server_default="other", index=True)
    due_date: Mapped[date] = mapped_column(Date, index=True)
    due_time: Mapped[time | None] = mapped_column(Time)
    priority: Mapped[TaskPriority] = mapped_column(_PRIORITY, server_default="normal")
    status: Mapped[TaskStatus] = mapped_column(_STATUS, server_default="pending", index=True)

    contract_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("contracts.id", ondelete="CASCADE"), index=True
    )
    minor_contract_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("minor_contracts.id", ondelete="CASCADE"), index=True
    )
    department_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("departments.id", ondelete="SET NULL")
    )

    recurrence: Mapped[str | None] = mapped_column(String(255))  # RRULE
    parent_task_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("tasks.id", ondelete="SET NULL")
    )

    created_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )
    completed_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution_notes: Mapped[str | None] = mapped_column(Text)

    assignees: Mapped[list[User]] = relationship(secondary=task_assignees)
    reminders: Mapped[list["TaskReminder"]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )


class TaskReminder(Base, TimestampMixin):
    """Definició i registre d'enviament en una sola fila per ocurrència."""

    __tablename__ = "task_reminders"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    task_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tasks.id", ondelete="CASCADE"), index=True
    )
    offset_days: Mapped[int] = mapped_column(Integer)  # abans del venciment; 0 = el dia mateix
    channel: Mapped[ReminderChannel] = mapped_column(_CHANNEL, server_default="email")
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    task: Mapped[Task] = relationship(back_populates="reminders")


class TaskHistoryEntry(Base):
    __tablename__ = "task_history"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    task_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tasks.id", ondelete="CASCADE"), index=True
    )
    field: Mapped[str] = mapped_column(String(100))
    old_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)
    user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


def snapshot(task: Task) -> dict[str, Any]:
    """Valors comparables per a l'historial del PATCH."""
    return {
        "title": task.title,
        "description": task.description,
        "task_type": task.task_type.value,
        "due_date": str(task.due_date),
        "due_time": str(task.due_time) if task.due_time else None,
        "priority": task.priority.value,
        "department_id": task.department_id,
        "recurrence": task.recurrence,
    }
