"""Casos d'ús de tasques (specs/tasks-core.md).

Abast: ALL tot; DEPT tasques d'expedients del seu àmbit, creades per ell
o assignades; ASSIGNED només les assignades. Fora d'abast → 404.
"""

from datetime import UTC, date, datetime
from typing import Any

from dateutil.rrule import rrulestr
from sqlalchemy import ColumnElement, Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core import authz
from app.core.pagination import decode_cursor, encode_cursor
from app.core.problems import Problem
from app.modules.audit.models import AuditActorType
from app.modules.audit.service import record_audit
from app.modules.contracts.models import Contract, contract_departments
from app.modules.minor_contracts.models import minor_contract_departments
from app.modules.tasks.models import (
    Task,
    TaskHistoryEntry,
    TaskReminder,
    TaskStatus,
    TaskType,
    snapshot,
    task_assignees,
)
from app.modules.tasks.schemas import TaskCreate, TaskUpdate
from app.modules.users.models import User
from app.modules.users.service import RequestContext

_LOAD = (selectinload(Task.assignees), selectinload(Task.reminders))


def _not_found() -> Problem:
    return Problem(404, "Tasca no trobada", "not-found")


def _assigned_predicate(user_id: int) -> ColumnElement[bool]:
    return Task.id.in_(select(task_assignees.c.task_id).where(task_assignees.c.user_id == user_id))


def _dept_predicate(department_ids: list[int], user_id: int) -> ColumnElement[bool]:
    if not department_ids:
        return or_(_assigned_predicate(user_id), Task.created_by == user_id)
    contracts_in_scope = select(contract_departments.c.contract_id).where(
        contract_departments.c.department_id.in_(department_ids)
    )
    minors_in_scope = select(minor_contract_departments.c.minor_contract_id).where(
        minor_contract_departments.c.department_id.in_(department_ids)
    )
    return or_(
        Task.contract_id.in_(contracts_in_scope),
        Task.minor_contract_id.in_(minors_in_scope),
        Task.department_id.in_(department_ids),
        Task.created_by == user_id,
        _assigned_predicate(user_id),
    )


def visibility_predicate(user: User, grant: authz.Grant) -> ColumnElement[bool] | None:
    if grant.access == authz.Access.ALL:
        return None
    if grant.access == authz.Access.ASSIGNED:
        return _assigned_predicate(user.id)
    return _dept_predicate([d.id for d in user.departments], user.id)


def _require(user: User, action: str) -> authz.Grant:
    grant = authz.evaluate(user, action)
    if grant is None:
        raise Problem(403, "Sense permís per a aquesta acció", "forbidden")
    return grant


async def get_visible_task(session: AsyncSession, task_id: int, user: User) -> Task:
    grant = _require(user, "tasks:read")
    stmt = select(Task).options(*_LOAD).where(Task.id == task_id)
    predicate = visibility_predicate(user, grant)
    if predicate is not None:
        stmt = stmt.where(predicate)
    task = (await session.execute(stmt)).scalar_one_or_none()
    if task is None:
        raise _not_found()
    return task


def _apply_filters(stmt: Select[Any], filters: dict[str, Any]) -> Select[Any]:
    if status := filters.get("status"):
        stmt = stmt.where(Task.status == status)
    if (due_before := filters.get("due_before")) is not None:
        stmt = stmt.where(Task.due_date <= due_before)
    if (due_after := filters.get("due_after")) is not None:
        stmt = stmt.where(Task.due_date >= due_after)
    if contract_id := filters.get("contract_id"):
        stmt = stmt.where(Task.contract_id == contract_id)
    if minor_id := filters.get("minor_contract_id"):
        stmt = stmt.where(Task.minor_contract_id == minor_id)
    if assignee_id := filters.get("assignee_id"):
        stmt = stmt.where(
            Task.id.in_(
                select(task_assignees.c.task_id).where(task_assignees.c.user_id == assignee_id)
            )
        )
    if department_id := filters.get("department_id"):
        stmt = stmt.where(Task.department_id == department_id)
    return stmt


async def list_tasks(
    session: AsyncSession,
    user: User,
    *,
    filters: dict[str, Any],
    page_size: int = 50,
    cursor: str | None = None,
) -> tuple[list[Task], int, str | None]:
    grant = _require(user, "tasks:read")
    base = select(Task)
    predicate = visibility_predicate(user, grant)
    if predicate is not None:
        base = base.where(predicate)
    base = _apply_filters(base, filters)

    total = (await session.execute(select(func.count()).select_from(base.subquery()))).scalar_one()

    stmt = base.options(*_LOAD).order_by(Task.due_date.asc(), Task.id.asc())
    if cursor is not None:
        from app.core.pagination import keyset_condition

        last_value, last_id = decode_cursor(cursor)
        stmt = stmt.where(
            keyset_condition(Task.due_date, Task.id, last_value, last_id, descending=False)
        )
    rows = list((await session.execute(stmt.limit(page_size + 1))).scalars())
    next_cursor = None
    if len(rows) > page_size:
        rows = rows[:page_size]
        next_cursor = encode_cursor([str(rows[-1].due_date), rows[-1].id])
    return rows, total, next_cursor


async def _subject_in_scope(
    session: AsyncSession, user: User, grant: authz.Grant, data: TaskCreate
) -> None:
    """El contracte/menor associat ha de ser dins l'abast de qui escriu."""
    if data.contract_id is None and data.minor_contract_id is None:
        raise Problem(422, "Cal associar la tasca a un contracte o a un menor", "validation")
    if grant.access == authz.Access.ALL:
        scope = authz.ScopeInfo(type="all")
    else:
        scope = authz.scope_for(user)

    if data.contract_id is not None:
        from app.modules.contracts.repository import get_visible_contract

        if await get_visible_contract(session, data.contract_id, scope, user.id) is None:
            raise Problem(404, "Contracte no trobat", "not-found")
    if data.minor_contract_id is not None:
        from app.modules.minor_contracts.repository import get_visible_minor

        if await get_visible_minor(session, data.minor_contract_id, scope) is None:
            raise Problem(404, "Contracte menor no trobat", "not-found")


def _validate_rrule(recurrence: str | None) -> None:
    if not recurrence:
        return
    try:
        rrulestr(recurrence)
    except (ValueError, TypeError):
        raise Problem(422, "Recurrència RRULE invàlida", "validation") from None


async def _load_assignees(session: AsyncSession, ids: list[int]) -> list[User]:
    if not ids:
        return []
    users = list((await session.execute(select(User).where(User.id.in_(ids)))).scalars())
    if len(users) != len(set(ids)):
        raise Problem(422, "Algun assignat no existeix", "validation")
    return users


async def _audit(
    session: AsyncSession, user: User, action: str, task_id: int, ctx: RequestContext
) -> None:
    await record_audit(
        session,
        actor_type=AuditActorType.USER,
        action=action,
        success=True,
        actor_id=user.id,
        resource_type="task",
        resource_id=str(task_id),
        ip=ctx.ip,
        user_agent=ctx.user_agent,
        trace_id=ctx.trace_id,
    )


async def create_task(
    session: AsyncSession, data: TaskCreate, user: User, ctx: RequestContext
) -> Task:
    grant = _require(user, "tasks:write")
    await _subject_in_scope(session, user, grant, data)
    _validate_rrule(data.recurrence)

    task = Task(
        title=data.title,
        description=data.description,
        task_type=data.task_type,
        due_date=data.due_date,
        due_time=data.due_time,
        priority=data.priority,
        contract_id=data.contract_id,
        minor_contract_id=data.minor_contract_id,
        department_id=data.department_id,
        recurrence=data.recurrence,
        created_by=user.id,
        assignees=await _load_assignees(session, data.assignee_ids),
    )
    for spec in data.reminders:
        task.reminders.append(TaskReminder(offset_days=spec.offset_days, channel=spec.channel))
    session.add(task)
    await session.flush()
    session.add(
        TaskHistoryEntry(task_id=task.id, field="status", new_value="pending", user_id=user.id)
    )
    await _audit(session, user, "tasks.create", task.id, ctx)
    await session.commit()
    return await get_visible_task(session, task.id, user)


async def _can_edit(session: AsyncSession, task: Task, user: User) -> bool:
    grant = authz.evaluate(user, "tasks:write")
    if grant is None:
        return False
    if grant.access == authz.Access.ALL:
        return True
    # DEPT: el subjecte de la tasca dins del seu àmbit, o creada per ell.
    if task.created_by == user.id:
        return True
    department_ids = [d.id for d in user.departments]
    if not department_ids:
        return False
    result = await session.execute(
        select(Task.id).where(Task.id == task.id, _dept_predicate(department_ids, user.id)).limit(1)
    )
    return result.first() is not None


async def update_task(
    session: AsyncSession, task_id: int, data: TaskUpdate, user: User, ctx: RequestContext
) -> Task:
    task = await get_visible_task(session, task_id, user)
    if not await _can_edit(session, task, user):
        raise Problem(403, "Sense permís per editar aquesta tasca", "forbidden")
    _validate_rrule(data.recurrence)

    before = snapshot(task)
    changes = data.model_dump(exclude_unset=True)
    assignee_ids = changes.pop("assignee_ids", None)
    reminder_specs = changes.pop("reminders", None)

    for field, value in changes.items():
        setattr(task, field, value)
    after = snapshot(task)
    for field in before:
        if before[field] != after[field]:
            session.add(
                TaskHistoryEntry(
                    task_id=task.id,
                    field=field,
                    old_value=str(before[field]) if before[field] is not None else None,
                    new_value=str(after[field]) if after[field] is not None else None,
                    user_id=user.id,
                )
            )

    if assignee_ids is not None:
        task.assignees = await _load_assignees(session, assignee_ids)
        session.add(
            TaskHistoryEntry(
                task_id=task.id,
                field="assignees",
                new_value=", ".join(str(i) for i in assignee_ids) or None,
                user_id=user.id,
            )
        )
    if reminder_specs is not None:
        unsent = [r for r in task.reminders if r.sent_at is None]
        for reminder in unsent:
            task.reminders.remove(reminder)
        for spec in reminder_specs:
            task.reminders.append(
                TaskReminder(offset_days=spec["offset_days"], channel=spec["channel"])
            )

    await session.flush()
    await _audit(session, user, "tasks.update", task.id, ctx)
    await session.commit()
    return await get_visible_task(session, task_id, user)


async def delete_task(session: AsyncSession, task_id: int, user: User, ctx: RequestContext) -> None:
    task = await get_visible_task(session, task_id, user)
    if not await _can_edit(session, task, user):
        raise Problem(403, "Sense permís per esborrar aquesta tasca", "forbidden")
    await session.delete(task)
    await session.flush()
    await _audit(session, user, "tasks.delete", task_id, ctx)
    await session.commit()


def _next_occurrence(task: Task) -> date | None:
    if not task.recurrence:
        return None
    try:
        rule = rrulestr(
            task.recurrence, dtstart=datetime.combine(task.due_date, datetime.min.time())
        )
        nxt = rule.after(datetime.combine(task.due_date, datetime.min.time()), inc=False)
    except (ValueError, TypeError):
        return None
    return nxt.date() if nxt is not None else None


async def change_status(
    session: AsyncSession,
    task_id: int,
    action: str,
    user: User,
    ctx: RequestContext,
    *,
    resolution_notes: str | None = None,
) -> Task:
    task = await get_visible_task(session, task_id, user)

    is_assignee = any(u.id == user.id for u in task.assignees)
    if not is_assignee and not await _can_edit(session, task, user):
        # tasks:update_status ASSIGNED: només si hi està assignat.
        raise Problem(403, "Només els assignats o qui pot editar", "forbidden")

    transitions = {
        "complete": (TaskStatus.PENDING, TaskStatus.IN_PROGRESS),
        "cancel": (TaskStatus.PENDING, TaskStatus.IN_PROGRESS),
        "reopen": (TaskStatus.DONE, TaskStatus.CANCELLED),
        "start": (TaskStatus.PENDING,),
    }
    if task.status not in transitions[action]:
        raise Problem(409, "Transició d'estat no permesa", "conflict")

    old_status = task.status.value
    if action == "complete":
        task.status = TaskStatus.DONE
        task.completed_by = user.id
        task.completed_at = datetime.now(UTC)
        task.resolution_notes = resolution_notes
    elif action == "cancel":
        task.status = TaskStatus.CANCELLED
        task.resolution_notes = resolution_notes
    elif action == "start":
        task.status = TaskStatus.IN_PROGRESS
    else:
        task.status = TaskStatus.PENDING
        task.completed_by = None
        task.completed_at = None

    session.add(
        TaskHistoryEntry(
            task_id=task.id,
            field="status",
            old_value=old_status,
            new_value=task.status.value,
            user_id=user.id,
        )
    )

    # Recurrència: completar genera la següent ocurrència.
    if action == "complete" and (next_due := _next_occurrence(task)) is not None:
        follow_up = Task(
            title=task.title,
            description=task.description,
            task_type=task.task_type,
            due_date=next_due,
            due_time=task.due_time,
            priority=task.priority,
            contract_id=task.contract_id,
            minor_contract_id=task.minor_contract_id,
            department_id=task.department_id,
            recurrence=task.recurrence,
            parent_task_id=task.parent_task_id or task.id,
            created_by=task.created_by,
            assignees=list(task.assignees),
        )
        for reminder in task.reminders:
            follow_up.reminders.append(
                TaskReminder(offset_days=reminder.offset_days, channel=reminder.channel)
            )
        session.add(follow_up)

    await session.flush()
    await _audit(session, user, f"tasks.{action}", task.id, ctx)
    await session.commit()
    return await get_visible_task(session, task_id, user)


_SUGGESTION_TITLES = {
    TaskType.EXTENSION: "Tramitar pròrroga o revisar venciment",
    TaskType.SETTLEMENT: "Revisar finalització i liquidació",
}


async def suggestions(session: AsyncSession, user: User) -> list[dict[str, Any]]:
    """Tasques proposades per les alertes, dins l'abast de contractes."""
    _require(user, "tasks:read")
    contract_grant = authz.evaluate(user, "contracts:read")
    if contract_grant is None:
        return []
    scope = (
        authz.ScopeInfo(type="all")
        if contract_grant.access == authz.Access.ALL
        else authz.scope_for(user)
    )
    from app.modules.contracts.repository import visibility_predicate as contract_visibility

    predicate = contract_visibility(scope, user.id)

    results: list[dict[str, Any]] = []
    for flag, task_type in (
        (Contract.expiry_warning, TaskType.EXTENSION),
        (Contract.possibly_finished, TaskType.SETTLEMENT),
    ):
        open_same_type = select(Task.contract_id).where(
            Task.task_type == task_type,
            Task.status.in_([TaskStatus.PENDING, TaskStatus.IN_PROGRESS]),
            Task.contract_id.is_not(None),
        )
        stmt = (
            select(Contract.id, Contract.file_code, Contract.subject, Contract.calculated_end_date)
            .where(flag, ~Contract.id.in_(open_same_type))
            .order_by(Contract.calculated_end_date.asc().nulls_last())
            .limit(50)
        )
        if predicate is not None:
            stmt = stmt.where(predicate)
        for row in (await session.execute(stmt)).all():
            results.append(
                {
                    "contract_id": row.id,
                    "file_code": row.file_code,
                    "subject": row.subject,
                    "task_type": task_type.value,
                    "title": f"{_SUGGESTION_TITLES[task_type]} — {row.file_code}",
                    "due_date": row.calculated_end_date,
                }
            )
    return results
