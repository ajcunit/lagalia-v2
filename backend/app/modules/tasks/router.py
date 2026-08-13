"""Endpoints de tasques. Prims: abast i regles al servei."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import authz
from app.core.db import get_session
from app.core.pagination import PageMeta
from app.modules.tasks import service
from app.modules.tasks.models import TaskStatus
from app.modules.tasks.schemas import (
    PagedTasksResponse,
    TaskCompleteRequest,
    TaskCreate,
    TaskHistoryResponse,
    TaskResponse,
    TaskSuggestion,
    TaskUpdate,
)
from app.modules.tasks.service import get_visible_task
from app.modules.users.dependencies import (
    CurrentSession,
    get_current_session,
    get_request_context,
)
from app.modules.users.service import RequestContext

router = APIRouter(tags=["tasks"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
ContextDep = Annotated[RequestContext, Depends(get_request_context)]
CurrentDep = Annotated[CurrentSession, Depends(get_current_session)]
ReadDep = Annotated[authz.AuthzContext, Depends(authz.Authorize("tasks:read"))]
ResourceId = Annotated[int, Path(ge=1)]


@router.get("/tasks", operation_id="listTasks")
async def list_tasks(
    session: SessionDep,
    authz_ctx: ReadDep,
    page_size: Annotated[int, Query(alias="page[size]", ge=1, le=500)] = 50,
    page_cursor: Annotated[str | None, Query(alias="page[cursor]")] = None,
    status: Annotated[TaskStatus | None, Query()] = None,
    due_before: Annotated[date | None, Query()] = None,
    due_after: Annotated[date | None, Query()] = None,
    contract_id: Annotated[int | None, Query()] = None,
    minor_contract_id: Annotated[int | None, Query()] = None,
    assignee_id: Annotated[int | None, Query()] = None,
    department_id: Annotated[int | None, Query()] = None,
) -> PagedTasksResponse:
    tasks, total, next_cursor = await service.list_tasks(
        session,
        authz_ctx.user,
        filters={
            "status": status,
            "due_before": due_before,
            "due_after": due_after,
            "contract_id": contract_id,
            "minor_contract_id": minor_contract_id,
            "assignee_id": assignee_id,
            "department_id": department_id,
        },
        page_size=page_size,
        cursor=page_cursor,
    )
    return PagedTasksResponse(
        data=[TaskResponse.from_task(t) for t in tasks],
        meta=PageMeta(total=total, next_cursor=next_cursor),
    )


@router.get("/tasks/calendar", operation_id="getTasksCalendar")
async def tasks_calendar(
    session: SessionDep,
    authz_ctx: ReadDep,
    from_: Annotated[date, Query(alias="from")],
    to: Annotated[date, Query()],
    department_id: Annotated[int | None, Query()] = None,
) -> dict[str, list[TaskResponse]]:
    tasks, _, _ = await service.list_tasks(
        session,
        authz_ctx.user,
        filters={"due_after": from_, "due_before": to, "department_id": department_id},
        page_size=500,
    )
    return {"data": [TaskResponse.from_task(t) for t in tasks]}


@router.get("/tasks/suggestions", operation_id="getTaskSuggestions")
async def task_suggestions(
    session: SessionDep, authz_ctx: ReadDep
) -> dict[str, list[TaskSuggestion]]:
    rows = await service.suggestions(session, authz_ctx.user)
    return {"data": [TaskSuggestion.model_validate(r) for r in rows]}


@router.post("/tasks", operation_id="createTask", status_code=201)
async def create_task(
    body: TaskCreate, session: SessionDep, current: CurrentDep, ctx: ContextDep
) -> TaskResponse:
    task = await service.create_task(session, body, current.user, ctx)
    return TaskResponse.from_task(task)


@router.get("/tasks/{id}", operation_id="getTask")
async def get_task(id: ResourceId, session: SessionDep, current: CurrentDep) -> TaskResponse:
    return TaskResponse.from_task(await get_visible_task(session, id, current.user))


@router.patch("/tasks/{id}", operation_id="updateTask")
async def update_task(
    id: ResourceId,
    body: TaskUpdate,
    session: SessionDep,
    current: CurrentDep,
    ctx: ContextDep,
) -> TaskResponse:
    task = await service.update_task(session, id, body, current.user, ctx)
    return TaskResponse.from_task(task)


@router.delete("/tasks/{id}", operation_id="deleteTask", status_code=204)
async def delete_task(
    id: ResourceId, session: SessionDep, current: CurrentDep, ctx: ContextDep
) -> None:
    await service.delete_task(session, id, current.user, ctx)


@router.post("/tasks/{id}/actions/complete", operation_id="completeTask")
async def complete_task(
    id: ResourceId,
    session: SessionDep,
    current: CurrentDep,
    ctx: ContextDep,
    body: TaskCompleteRequest | None = None,
) -> TaskResponse:
    task = await service.change_status(
        session,
        id,
        "complete",
        current.user,
        ctx,
        resolution_notes=body.resolution_notes if body else None,
    )
    return TaskResponse.from_task(task)


@router.post("/tasks/{id}/actions/cancel", operation_id="cancelTask")
async def cancel_task(
    id: ResourceId,
    session: SessionDep,
    current: CurrentDep,
    ctx: ContextDep,
    body: TaskCompleteRequest | None = None,
) -> TaskResponse:
    task = await service.change_status(
        session,
        id,
        "cancel",
        current.user,
        ctx,
        resolution_notes=body.resolution_notes if body else None,
    )
    return TaskResponse.from_task(task)


@router.post("/tasks/{id}/actions/reopen", operation_id="reopenTask")
async def reopen_task(
    id: ResourceId, session: SessionDep, current: CurrentDep, ctx: ContextDep
) -> TaskResponse:
    task = await service.change_status(session, id, "reopen", current.user, ctx)
    return TaskResponse.from_task(task)


@router.post("/tasks/{id}/actions/start", operation_id="startTask")
async def start_task(
    id: ResourceId, session: SessionDep, current: CurrentDep, ctx: ContextDep
) -> TaskResponse:
    task = await service.change_status(session, id, "start", current.user, ctx)
    return TaskResponse.from_task(task)


@router.get("/tasks/{id}/history", operation_id="getTaskHistory")
async def get_task_history(
    id: ResourceId, session: SessionDep, current: CurrentDep
) -> dict[str, list[TaskHistoryResponse]]:
    from sqlalchemy import select

    from app.modules.tasks.models import TaskHistoryEntry

    await get_visible_task(session, id, current.user)
    entries = (
        await session.execute(
            select(TaskHistoryEntry)
            .where(TaskHistoryEntry.task_id == id)
            .order_by(TaskHistoryEntry.id.desc())
        )
    ).scalars()
    return {"data": [TaskHistoryResponse.from_entry(e) for e in entries]}
