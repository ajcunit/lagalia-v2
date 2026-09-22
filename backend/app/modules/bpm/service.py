"""Motor BPM (specs/bpm.md): arrencada i avanç d'instàncies.

L'avanç és per escaneig (job bpm.scan), no per hook al mòdul de tasques:
cap acoblament nou, i una tasca completada fa aparèixer la següent com a
molt una hora després — el ritme el manen els offset_days, no el minut.
"""

from datetime import UTC, date, datetime, timedelta

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.problems import Problem
from app.modules.bpm.models import (
    BpmAssigneeKind,
    BpmInstance,
    BpmInstanceStatus,
    BpmStep,
    BpmTrigger,
    BpmWorkflow,
)
from app.modules.bpm.schemas import BpmWorkflowInput
from app.modules.contracts.models import Contract
from app.modules.tasks.models import Task, TaskStatus
from app.modules.users.models import User

logger = structlog.get_logger()

# Fre de seguretat: mai més de N arrencades per procés i passada (un procés
# nou sobre un fons de milers d'expedients no pot inundar les tasques).
MAX_STARTS_PER_SCAN = 200

_WORKFLOW_LOAD = (selectinload(BpmWorkflow.steps),)


async def get_workflow(session: AsyncSession, workflow_id: int) -> BpmWorkflow:
    workflow = (
        await session.execute(
            select(BpmWorkflow).options(*_WORKFLOW_LOAD).where(BpmWorkflow.id == workflow_id)
        )
    ).scalar_one_or_none()
    if workflow is None:
        raise Problem(404, "Procés no trobat", "not-found")
    return workflow


async def list_workflows(session: AsyncSession) -> list[BpmWorkflow]:
    return list(
        (
            await session.execute(
                select(BpmWorkflow).options(*_WORKFLOW_LOAD).order_by(BpmWorkflow.name)
            )
        ).scalars()
    )


def _steps_from_input(data: BpmWorkflowInput) -> list[BpmStep]:
    return [
        BpmStep(
            position=index,
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
        for index, step in enumerate(data.steps, start=1)
    ]


async def create_workflow(
    session: AsyncSession, data: BpmWorkflowInput, created_by: int
) -> BpmWorkflow:
    workflow = BpmWorkflow(
        name=data.name,
        description=data.description,
        trigger=data.trigger,
        trigger_status=data.trigger_status,
        active=data.active,
        created_by=created_by,
        steps=_steps_from_input(data),
    )
    session.add(workflow)
    await session.flush()
    return workflow


async def update_workflow(
    session: AsyncSession, workflow_id: int, data: BpmWorkflowInput
) -> BpmWorkflow:
    workflow = await get_workflow(session, workflow_id)
    workflow.name = data.name
    workflow.description = data.description
    workflow.trigger = data.trigger
    workflow.trigger_status = data.trigger_status
    workflow.active = data.active
    # Substitució sencera dels passos: les instàncies en marxa conserven la
    # seva posició; si el procés s'escurça, l'avanç les tancarà com a done.
    workflow.steps = _steps_from_input(data)
    await session.flush()
    return workflow


def _resolve_due(base: date, offset_days: int) -> date:
    due = base + timedelta(days=offset_days)
    today = datetime.now(UTC).date()
    return due if due >= today else today


async def _assignees_for_step(session: AsyncSession, step: BpmStep) -> list[User]:
    if step.assignee_kind == BpmAssigneeKind.USER and step.assignee_user_id is not None:
        user = await session.get(User, step.assignee_user_id)
        return [user] if user is not None and user.active else []
    if step.assignee_kind == BpmAssigneeKind.ROLE and step.assignee_role is not None:
        return list(
            (
                await session.execute(
                    select(User).where(User.role == step.assignee_role, User.active.is_(True))
                )
            ).scalars()
        )
    return []  # department: la tasca queda al departament, sense assignats


async def _create_step_task(
    session: AsyncSession,
    workflow: BpmWorkflow,
    instance: BpmInstance,
    step: BpmStep,
    base: date,
) -> Task:
    task = Task(
        title=step.title,
        description=step.description or f"Pas {step.position} del procés «{workflow.name}» (BPM)",
        task_type=step.task_type,
        due_date=_resolve_due(base, step.offset_days),
        priority=step.priority,
        contract_id=instance.contract_id,
        department_id=(
            step.assignee_department_id
            if step.assignee_kind == BpmAssigneeKind.DEPARTMENT
            else None
        ),
        created_by=workflow.created_by,
        assignees=await _assignees_for_step(session, step),
    )
    session.add(task)
    await session.flush()
    return task


async def start_instance(
    session: AsyncSession, workflow: BpmWorkflow, contract_id: int
) -> BpmInstance | None:
    """Obre una instància i la primera tasca; None si ja n'hi ha una."""
    existing = (
        await session.execute(
            select(BpmInstance.id).where(
                BpmInstance.workflow_id == workflow.id, BpmInstance.contract_id == contract_id
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return None
    if not workflow.steps:
        return None

    instance = BpmInstance(
        workflow_id=workflow.id,
        contract_id=contract_id,
        current_position=1,
        started_at=datetime.now(UTC),
    )
    session.add(instance)
    await session.flush()
    first = workflow.steps[0]
    task = await _create_step_task(session, workflow, instance, first, datetime.now(UTC).date())
    instance.current_task_id = task.id
    await session.flush()
    return instance


async def advance_instance(session: AsyncSession, instance: BpmInstance) -> str:
    """Avança una instància segons l'estat de la seva tasca actual.

    Retorna què ha passat: kept | advanced | done | cancelled."""
    workflow = await get_workflow(session, instance.workflow_id)

    task = (
        await session.get(Task, instance.current_task_id)
        if instance.current_task_id is not None
        else None
    )
    if task is None or task.status == TaskStatus.CANCELLED:
        # Tasca esborrada o cancel·lada: el procés s'atura (specs/bpm.md).
        instance.status = BpmInstanceStatus.CANCELLED
        instance.finished_at = datetime.now(UTC)
        await session.flush()
        return "cancelled"
    if task.status != TaskStatus.DONE:
        return "kept"

    completed_on = (task.completed_at or datetime.now(UTC)).date()
    next_step = next((s for s in workflow.steps if s.position > instance.current_position), None)
    if next_step is None:
        instance.status = BpmInstanceStatus.DONE
        instance.finished_at = datetime.now(UTC)
        await session.flush()
        return "done"

    new_task = await _create_step_task(session, workflow, instance, next_step, completed_on)
    instance.current_position = next_step.position
    instance.current_task_id = new_task.id
    await session.flush()
    return "advanced"


async def contracts_matching_trigger(session: AsyncSession, workflow: BpmWorkflow) -> list[int]:
    """Contractes que compleixen el disparador i encara no tenen instància.

    Guarda contra l'històric: només contractes posteriors al procés
    (contract_created) o actualitzats després de crear-lo (status_reached)."""
    if workflow.trigger == BpmTrigger.MANUAL:
        return []
    with_instance = (
        select(BpmInstance.contract_id)
        .where(BpmInstance.workflow_id == workflow.id)
        .scalar_subquery()
    )
    stmt = select(Contract.id).where(Contract.id.not_in(with_instance))
    if workflow.trigger == BpmTrigger.CONTRACT_CREATED:
        stmt = stmt.where(Contract.created_at > workflow.created_at)
    else:
        stmt = stmt.where(
            Contract.status == (workflow.trigger_status or ""),
            Contract.updated_at > workflow.created_at,
        )
    stmt = stmt.order_by(Contract.id).limit(MAX_STARTS_PER_SCAN + 1)
    return list((await session.execute(stmt)).scalars())
