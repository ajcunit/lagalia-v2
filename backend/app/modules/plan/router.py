"""Pla anual de contractació (specs/annual-plan.md).

Workflow: no-admins creen/editen en pending; aprovar és plan:approve.
"""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import extract, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import authz
from app.core.db import get_session
from app.core.problems import Problem
from app.modules.audit.models import AuditActorType
from app.modules.audit.service import record_audit
from app.modules.contracts.models import Contract
from app.modules.departments.models import Department
from app.modules.plan.models import PlanEntry, PlanStatus
from app.modules.users.dependencies import get_request_context
from app.modules.users.models import UserRole
from app.modules.users.service import RequestContext

router = APIRouter(tags=["plan"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
ContextDep = Annotated[RequestContext, Depends(get_request_context)]
ReadDep = Annotated[authz.AuthzContext, Depends(authz.Authorize("plan:read"))]
WriteDep = Annotated[authz.AuthzContext, Depends(authz.Authorize("plan:write"))]
ApproveDep = Annotated[authz.AuthzContext, Depends(authz.Authorize("plan:approve"))]

Year = Annotated[int, Query(ge=2000, le=2100)]


class PlanBody(BaseModel):
    fiscal_year: int = Field(ge=2000, le=2100)
    quarter: int = Field(ge=1, le=4)
    subject: str = Field(min_length=1, max_length=1000)
    contract_type: str | None = Field(default=None, max_length=100)
    scope: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None, max_length=2000)
    subsidized: bool = False
    estimated_amount: Decimal | None = Field(default=None, ge=0)
    department_id: int | None = None
    contract_id: int | None = None


class PlanPatch(BaseModel):
    quarter: int | None = Field(default=None, ge=1, le=4)
    subject: str | None = Field(default=None, min_length=1, max_length=1000)
    contract_type: str | None = Field(default=None, max_length=100)
    scope: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None, max_length=2000)
    subsidized: bool | None = None
    estimated_amount: Decimal | None = Field(default=None, ge=0)
    department_id: int | None = None
    contract_id: int | None = None


class PlanResponse(BaseModel):
    id: int
    fiscal_year: int
    quarter: int
    subject: str
    contract_type: str | None
    scope: str | None
    notes: str | None
    subsidized: bool
    estimated_amount: Decimal | None
    status: PlanStatus
    department_id: int | None
    department_name: str | None = None
    contract_id: int | None
    contract_file_code: str | None = None
    created_by: int | None
    created_at: datetime


async def _entry_response(session: AsyncSession, entry: PlanEntry) -> PlanResponse:
    dept = (
        await session.execute(select(Department.name).where(Department.id == entry.department_id))
    ).scalar_one_or_none() if entry.department_id else None
    code = (
        await session.execute(select(Contract.file_code).where(Contract.id == entry.contract_id))
    ).scalar_one_or_none() if entry.contract_id else None
    base = PlanResponse.model_validate(entry, from_attributes=True)
    base.department_name = dept
    base.contract_file_code = code
    return base


async def _audit(
    session: AsyncSession, user_id: int, action: str, resource: str, ctx: RequestContext
) -> None:
    await record_audit(
        session, actor_type=AuditActorType.USER, action=action, success=True,
        actor_id=user_id, resource_type="plan", resource_id=resource,
        ip=ctx.ip, user_agent=ctx.user_agent, trace_id=ctx.trace_id,
    )


async def _own_entry(session: AsyncSession, id: int) -> PlanEntry:
    entry = await session.get(PlanEntry, id)
    if entry is None:
        raise Problem(404, "Entrada de pla desconeguda", "not-found")
    return entry


@router.get("/plan", operation_id="listPlanEntries")
async def list_plan(
    session: SessionDep, _authz: ReadDep, fiscal_year: Year
) -> dict[str, list[PlanResponse]]:
    entries = (
        await session.execute(
            select(PlanEntry)
            .where(PlanEntry.fiscal_year == fiscal_year)
            .order_by(PlanEntry.quarter, PlanEntry.id)
        )
    ).scalars()
    return {"data": [await _entry_response(session, e) for e in entries]}


@router.post("/plan", operation_id="createPlanEntry", status_code=201)
async def create_plan_entry(
    body: PlanBody, session: SessionDep, authz_ctx: WriteDep, ctx: ContextDep
) -> PlanResponse:
    is_admin = authz_ctx.user.role == UserRole.ADMIN
    entry = PlanEntry(
        **body.model_dump(),
        status=PlanStatus.APPROVED if is_admin else PlanStatus.PENDING,
        created_by=authz_ctx.user.id,
    )
    session.add(entry)
    await session.flush()
    await _audit(session, authz_ctx.user.id, "plan.entry_created", str(entry.id), ctx)
    await session.commit()
    return await _entry_response(session, entry)


@router.patch("/plan/{id}", operation_id="updatePlanEntry")
async def update_plan_entry(
    id: int, body: PlanPatch, session: SessionDep, authz_ctx: WriteDep, ctx: ContextDep
) -> PlanResponse:
    entry = await _own_entry(session, id)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(entry, key, value)
    # Editar una aprovada com a no-admin la retorna a pendent (02 §2.13).
    if authz_ctx.user.role != UserRole.ADMIN:
        entry.status = PlanStatus.PENDING
    await _audit(session, authz_ctx.user.id, "plan.entry_updated", str(id), ctx)
    await session.commit()
    return await _entry_response(session, entry)


@router.post("/plan/{id}/actions/approve", operation_id="approvePlanEntry")
async def approve_plan_entry(
    id: int, session: SessionDep, authz_ctx: ApproveDep, ctx: ContextDep
) -> PlanResponse:
    entry = await _own_entry(session, id)
    entry.status = PlanStatus.APPROVED
    await _audit(session, authz_ctx.user.id, "plan.entry_approved", str(id), ctx)
    await session.commit()
    return await _entry_response(session, entry)


@router.delete("/plan/{id}", operation_id="deletePlanEntry", status_code=204)
async def delete_plan_entry(
    id: int, session: SessionDep, authz_ctx: WriteDep, ctx: ContextDep
) -> None:
    entry = await _own_entry(session, id)
    if authz_ctx.user.role != UserRole.ADMIN and entry.created_by != authz_ctx.user.id:
        raise Problem(403, "Només l'autor o un admin poden esborrar l'entrada", "forbidden")
    await session.delete(entry)
    await _audit(session, authz_ctx.user.id, "plan.entry_deleted", str(id), ctx)
    await session.commit()


@router.get("/plan/expiring", operation_id="listPlanExpiring")
async def list_expiring(
    session: SessionDep, _authz: ReadDep, fiscal_year: Year
) -> dict[str, list[dict[str, Any]]]:
    """Contractes que caduquen dins l'exercici, per trimestre (exclou obres i anul·lats)."""
    quarter = extract("quarter", Contract.calculated_end_date)
    rows = (
        await session.execute(
            select(Contract.id, Contract.file_code, Contract.subject,
                   Contract.calculated_end_date, Contract.contract_type,
                   quarter.label("quarter"))
            .where(
                extract("year", Contract.calculated_end_date) == fiscal_year,
                func.lower(func.coalesce(Contract.contract_type, "")).not_like("%obres%"),
                func.lower(Contract.status).not_like("%anul%"),
            )
            .order_by(Contract.calculated_end_date)
            .limit(500)
        )
    ).all()
    return {
        "data": [
            {
                "contract_id": r.id,
                "file_code": r.file_code,
                "subject": r.subject,
                "end_date": r.calculated_end_date,
                "contract_type": r.contract_type,
                "quarter": int(r.quarter),
            }
            for r in rows
        ]
    }
