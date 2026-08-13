from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, Field

from app.core.pagination import PageMeta
from app.modules.tasks.models import (
    ReminderChannel,
    Task,
    TaskHistoryEntry,
    TaskPriority,
    TaskStatus,
    TaskType,
)


class AssigneeRef(BaseModel):
    id: int
    name: str


class ReminderSpec(BaseModel):
    offset_days: int = Field(ge=0, le=365)
    channel: ReminderChannel = ReminderChannel.EMAIL


class ReminderResponse(ReminderSpec):
    id: int
    sent_at: datetime | None = None


class TaskResponse(BaseModel):
    id: int
    title: str
    description: str | None = None
    task_type: TaskType
    due_date: date
    due_time: time | None = None
    priority: TaskPriority
    status: TaskStatus
    contract_id: int | None = None
    minor_contract_id: int | None = None
    department_id: int | None = None
    recurrence: str | None = None
    parent_task_id: int | None = None
    created_by: int | None = None
    completed_by: int | None = None
    completed_at: datetime | None = None
    resolution_notes: str | None = None
    assignees: list[AssigneeRef]
    reminders: list[ReminderResponse]
    created_at: datetime

    @classmethod
    def from_task(cls, task: Task) -> "TaskResponse":
        return cls(
            id=task.id,
            title=task.title,
            description=task.description,
            task_type=task.task_type,
            due_date=task.due_date,
            due_time=task.due_time,
            priority=task.priority,
            status=task.status,
            contract_id=task.contract_id,
            minor_contract_id=task.minor_contract_id,
            department_id=task.department_id,
            recurrence=task.recurrence,
            parent_task_id=task.parent_task_id,
            created_by=task.created_by,
            completed_by=task.completed_by,
            completed_at=task.completed_at,
            resolution_notes=task.resolution_notes,
            assignees=[AssigneeRef(id=u.id, name=u.name) for u in task.assignees],
            reminders=[
                ReminderResponse(
                    id=r.id, offset_days=r.offset_days, channel=r.channel, sent_at=r.sent_at
                )
                for r in task.reminders
            ],
            created_at=task.created_at,
        )


class TaskCreate(BaseModel):
    title: str = Field(min_length=2, max_length=255)
    description: str | None = None
    task_type: TaskType = TaskType.OTHER
    due_date: date
    due_time: time | None = None
    priority: TaskPriority = TaskPriority.NORMAL
    contract_id: int | None = None
    minor_contract_id: int | None = None
    department_id: int | None = None
    recurrence: str | None = Field(default=None, max_length=255)
    assignee_ids: list[int] = Field(default_factory=list, max_length=20)
    reminders: list[ReminderSpec] = Field(default_factory=list, max_length=10)


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=255)
    description: str | None = None
    task_type: TaskType | None = None
    due_date: date | None = None
    due_time: time | None = None
    priority: TaskPriority | None = None
    department_id: int | None = None
    recurrence: str | None = Field(default=None, max_length=255)
    assignee_ids: list[int] | None = Field(default=None, max_length=20)
    reminders: list[ReminderSpec] | None = Field(default=None, max_length=10)


class TaskCompleteRequest(BaseModel):
    resolution_notes: str | None = Field(default=None, max_length=2000)


class TaskHistoryResponse(BaseModel):
    id: int
    field: str
    old_value: str | None = None
    new_value: str | None = None
    user_id: int | None = None
    changed_at: datetime

    @classmethod
    def from_entry(cls, entry: TaskHistoryEntry) -> "TaskHistoryResponse":
        return cls(
            id=entry.id,
            field=entry.field,
            old_value=entry.old_value,
            new_value=entry.new_value,
            user_id=entry.user_id,
            changed_at=entry.changed_at,
        )


class TaskSuggestion(BaseModel):
    contract_id: int
    file_code: str
    subject: str | None = None
    task_type: Literal["extension", "settlement"]
    title: str
    due_date: date | None = None


class PagedTasksResponse(BaseModel):
    data: list[TaskResponse]
    meta: PageMeta
