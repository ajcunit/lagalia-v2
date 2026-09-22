"""Esquemes del mòdul BPM (specs/bpm.md)."""

from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.modules.bpm.models import (
    BpmAssigneeKind,
    BpmInstance,
    BpmInstanceStatus,
    BpmStep,
    BpmTrigger,
    BpmWorkflow,
)
from app.modules.tasks.models import TaskPriority, TaskType
from app.modules.users.models import UserRole


class BpmStepInput(BaseModel):
    title: str = Field(min_length=2, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    task_type: TaskType = TaskType.OTHER
    priority: TaskPriority = TaskPriority.NORMAL
    offset_days: int = Field(default=0, ge=0, le=365)
    assignee_kind: BpmAssigneeKind
    assignee_user_id: int | None = None
    assignee_department_id: int | None = None
    assignee_role: UserRole | None = None

    @model_validator(mode="after")
    def target_matches_kind(self) -> "BpmStepInput":
        targets = {
            BpmAssigneeKind.USER: self.assignee_user_id,
            BpmAssigneeKind.DEPARTMENT: self.assignee_department_id,
            BpmAssigneeKind.ROLE: self.assignee_role,
        }
        if targets[self.assignee_kind] is None:
            raise ValueError(f"falta l'objectiu per a l'assignació «{self.assignee_kind.value}»")
        return self


class BpmWorkflowInput(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    trigger: BpmTrigger
    trigger_status: str | None = Field(default=None, max_length=255)
    active: bool = True
    steps: list[BpmStepInput] = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def status_only_for_status_trigger(self) -> "BpmWorkflowInput":
        if self.trigger == BpmTrigger.STATUS_REACHED and not self.trigger_status:
            raise ValueError("el disparador per estat necessita trigger_status")
        return self


class BpmStepResponse(BaseModel):
    id: int
    position: int
    title: str
    description: str | None
    task_type: TaskType
    priority: TaskPriority
    offset_days: int
    assignee_kind: BpmAssigneeKind
    assignee_user_id: int | None
    assignee_department_id: int | None
    assignee_role: UserRole | None

    @classmethod
    def from_step(cls, step: BpmStep) -> "BpmStepResponse":
        return cls(
            id=step.id,
            position=step.position,
            title=step.title,
            description=step.description,
            task_type=step.task_type,
            priority=step.priority,
            offset_days=step.offset_days,
            assignee_kind=step.assignee_kind,
            assignee_user_id=step.assignee_user_id,
            assignee_department_id=step.assignee_department_id,
            assignee_role=step.assignee_role,
        )


class BpmWorkflowResponse(BaseModel):
    id: int
    name: str
    description: str | None
    trigger: BpmTrigger
    trigger_status: str | None
    active: bool
    steps: list[BpmStepResponse]
    created_at: datetime

    @classmethod
    def from_workflow(cls, workflow: BpmWorkflow) -> "BpmWorkflowResponse":
        return cls(
            id=workflow.id,
            name=workflow.name,
            description=workflow.description,
            trigger=workflow.trigger,
            trigger_status=workflow.trigger_status,
            active=workflow.active,
            steps=[BpmStepResponse.from_step(s) for s in workflow.steps],
            created_at=workflow.created_at,
        )


class BpmInstanceResponse(BaseModel):
    id: int
    workflow_id: int
    contract_id: int
    status: BpmInstanceStatus
    current_position: int
    current_task_id: int | None
    started_at: datetime | None
    finished_at: datetime | None

    @classmethod
    def from_instance(cls, instance: BpmInstance) -> "BpmInstanceResponse":
        return cls(
            id=instance.id,
            workflow_id=instance.workflow_id,
            contract_id=instance.contract_id,
            status=instance.status,
            current_position=instance.current_position,
            current_task_id=instance.current_task_id,
            started_at=instance.started_at,
            finished_at=instance.finished_at,
        )
