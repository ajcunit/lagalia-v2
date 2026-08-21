"""Processos BPM: seqüències de tasques per expedient (specs/bpm.md).

Un procés és una seqüència LINEAL de passos; cada instància viu sobre un
contracte i avança quan la tasca del pas actual es completa. Les tasques
generades són tasques normals: recordatoris, calendari i avisos existents
s'hi apliquen sense codi nou.
"""

import enum
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Identity,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.core.models import TimestampMixin
from app.modules.tasks.models import TaskPriority, TaskType
from app.modules.users.models import UserRole


class BpmTrigger(enum.StrEnum):
    CONTRACT_CREATED = "contract_created"
    STATUS_REACHED = "status_reached"
    MANUAL = "manual"


class BpmAssigneeKind(enum.StrEnum):
    USER = "user"
    DEPARTMENT = "department"
    ROLE = "role"


class BpmInstanceStatus(enum.StrEnum):
    RUNNING = "running"
    DONE = "done"
    CANCELLED = "cancelled"


_TRIGGER = Enum(BpmTrigger, name="bpm_trigger", values_callable=lambda e: [m.value for m in e])
_KIND = Enum(
    BpmAssigneeKind, name="bpm_assignee_kind", values_callable=lambda e: [m.value for m in e]
)
_INSTANCE_STATUS = Enum(
    BpmInstanceStatus, name="bpm_instance_status", values_callable=lambda e: [m.value for m in e]
)


class BpmWorkflow(Base, TimestampMixin):
    __tablename__ = "bpm_workflows"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    trigger: Mapped[BpmTrigger] = mapped_column(_TRIGGER, index=True)
    # Estat de la font que dispara el procés (només per a status_reached).
    trigger_status: Mapped[str | None] = mapped_column(String(255))
    active: Mapped[bool] = mapped_column(Boolean, server_default="true", index=True)
    created_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )

    steps: Mapped[list["BpmStep"]] = relationship(
        cascade="all, delete-orphan", order_by="BpmStep.position"
    )


class BpmStep(Base, TimestampMixin):
    __tablename__ = "bpm_steps"
    __table_args__ = (UniqueConstraint("workflow_id", "position", name="uq_bpm_steps_position"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    workflow_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("bpm_workflows.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    task_type: Mapped[TaskType] = mapped_column(
        Enum(TaskType, name="task_type", values_callable=lambda e: [m.value for m in e]),
        server_default="other",
    )
    priority: Mapped[TaskPriority] = mapped_column(
        Enum(TaskPriority, name="task_priority", values_callable=lambda e: [m.value for m in e]),
        server_default="normal",
    )
    # Dies des del disparador (primer pas) o des de la compleció de
    # l'anterior (la resta).
    offset_days: Mapped[int] = mapped_column(Integer, server_default="0")
    assignee_kind: Mapped[BpmAssigneeKind] = mapped_column(_KIND)
    assignee_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )
    assignee_department_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("departments.id", ondelete="SET NULL")
    )
    assignee_role: Mapped[UserRole | None] = mapped_column(
        Enum(UserRole, name="user_role", values_callable=lambda e: [m.value for m in e])
    )


class BpmInstance(Base, TimestampMixin):
    __tablename__ = "bpm_instances"
    __table_args__ = (
        UniqueConstraint("workflow_id", "contract_id", name="uq_bpm_instances_contract"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    workflow_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("bpm_workflows.id", ondelete="CASCADE"), index=True
    )
    contract_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("contracts.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[BpmInstanceStatus] = mapped_column(
        _INSTANCE_STATUS, server_default="running", index=True
    )
    current_position: Mapped[int] = mapped_column(Integer, server_default="1")
    current_task_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("tasks.id", ondelete="SET NULL")
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
