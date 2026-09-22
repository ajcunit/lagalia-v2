"""Endpoints del mòdul BPM (specs/bpm.md). Prims: la lògica és al servei."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import authz
from app.core.db import get_session
from app.core.problems import Problem
from app.modules.audit.models import AuditActorType
from app.modules.audit.service import record_audit
from app.modules.bpm import service
from app.modules.bpm.models import BpmInstance, BpmInstanceStatus
from app.modules.bpm.schemas import (
    BpmInstanceResponse,
    BpmWorkflowInput,
    BpmWorkflowResponse,
)
from app.modules.contracts.models import Contract
from app.modules.users.dependencies import get_request_context
from app.modules.users.service import RequestContext

router = APIRouter(prefix="/bpm", tags=["bpm"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
ContextDep = Annotated[RequestContext, Depends(get_request_context)]
ReadDep = Annotated[authz.AuthzContext, Depends(authz.Authorize("bpm:read"))]
ManageDep = Annotated[authz.AuthzContext, Depends(authz.Authorize("bpm:manage"))]
ResourceId = Annotated[int, Path(ge=1)]


async def _audit(
    session: AsyncSession, user_id: int, action: str, resource_id: str, ctx: RequestContext
) -> None:
    await record_audit(
        session,
        actor_type=AuditActorType.USER,
        action=action,
        success=True,
        actor_id=user_id,
        resource_type="bpm",
        resource_id=resource_id,
        ip=ctx.ip,
        user_agent=ctx.user_agent,
        trace_id=ctx.trace_id,
    )


@router.get("/workflows", operation_id="listBpmWorkflows")
async def list_workflows(
    session: SessionDep, _authz: ReadDep
) -> dict[str, list[BpmWorkflowResponse]]:
    workflows = await service.list_workflows(session)
    return {"data": [BpmWorkflowResponse.from_workflow(w) for w in workflows]}


@router.post("/workflows", operation_id="createBpmWorkflow", status_code=201)
async def create_workflow(
    body: BpmWorkflowInput, session: SessionDep, authz_ctx: ManageDep, ctx: ContextDep
) -> BpmWorkflowResponse:
    workflow = await service.create_workflow(session, body, authz_ctx.user.id)
    await _audit(session, authz_ctx.user.id, "bpm.workflow_create", str(workflow.id), ctx)
    await session.commit()
    return BpmWorkflowResponse.from_workflow(await service.get_workflow(session, workflow.id))


@router.put("/workflows/{id}", operation_id="updateBpmWorkflow")
async def update_workflow(
    id: ResourceId,
    body: BpmWorkflowInput,
    session: SessionDep,
    authz_ctx: ManageDep,
    ctx: ContextDep,
) -> BpmWorkflowResponse:
    workflow = await service.update_workflow(session, id, body)
    await _audit(session, authz_ctx.user.id, "bpm.workflow_update", str(workflow.id), ctx)
    await session.commit()
    return BpmWorkflowResponse.from_workflow(await service.get_workflow(session, id))


@router.delete("/workflows/{id}", operation_id="deleteBpmWorkflow", status_code=204)
async def delete_workflow(
    id: ResourceId, session: SessionDep, authz_ctx: ManageDep, ctx: ContextDep
) -> None:
    workflow = await service.get_workflow(session, id)
    await session.delete(workflow)
    await session.flush()
    await _audit(session, authz_ctx.user.id, "bpm.workflow_delete", str(id), ctx)
    await session.commit()


@router.post("/workflows/{id}/actions/start", operation_id="startBpmInstance", status_code=201)
async def start_instance(
    id: ResourceId,
    session: SessionDep,
    authz_ctx: ManageDep,
    ctx: ContextDep,
    contract_id: Annotated[int, Query(ge=1)],
) -> BpmInstanceResponse:
    """Arrencada manual d'un procés sobre un contracte."""
    workflow = await service.get_workflow(session, id)
    contract = await session.get(Contract, contract_id)
    if contract is None:
        raise Problem(404, "Contracte no trobat", "not-found")
    instance = await service.start_instance(session, workflow, contract_id)
    if instance is None:
        raise Problem(409, "Aquest contracte ja té una instància del procés", "conflict")
    await _audit(session, authz_ctx.user.id, "bpm.instance_start", str(instance.id), ctx)
    await session.commit()
    return BpmInstanceResponse.from_instance(instance)


@router.get("/instances", operation_id="listBpmInstances")
async def list_instances(
    session: SessionDep,
    _authz: ReadDep,
    workflow_id: Annotated[int | None, Query(ge=1)] = None,
    contract_id: Annotated[int | None, Query(ge=1)] = None,
) -> dict[str, list[BpmInstanceResponse]]:
    stmt = select(BpmInstance).order_by(BpmInstance.id.desc()).limit(200)
    if workflow_id is not None:
        stmt = stmt.where(BpmInstance.workflow_id == workflow_id)
    if contract_id is not None:
        stmt = stmt.where(BpmInstance.contract_id == contract_id)
    instances = list((await session.execute(stmt)).scalars())
    return {"data": [BpmInstanceResponse.from_instance(i) for i in instances]}


@router.post("/instances/{id}/actions/cancel", operation_id="cancelBpmInstance")
async def cancel_instance(
    id: ResourceId, session: SessionDep, authz_ctx: ManageDep, ctx: ContextDep
) -> BpmInstanceResponse:
    from datetime import UTC, datetime

    instance = await session.get(BpmInstance, id)
    if instance is None:
        raise Problem(404, "Instància no trobada", "not-found")
    if instance.status != BpmInstanceStatus.RUNNING:
        raise Problem(409, "La instància ja està acabada", "conflict")
    instance.status = BpmInstanceStatus.CANCELLED
    instance.finished_at = datetime.now(UTC)
    await session.flush()
    await _audit(session, authz_ctx.user.id, "bpm.instance_cancel", str(id), ctx)
    await session.commit()
    return BpmInstanceResponse.from_instance(instance)
