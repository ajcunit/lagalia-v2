"""Endpoints de contractes menors. Prims; abast al repositori."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import authz
from app.core.db import get_session
from app.core.pagination import PageMeta
from app.core.problems import Problem
from app.modules.audit.models import AuditActorType
from app.modules.audit.service import record_audit
from app.modules.contracts.models import InternalStatus
from app.modules.departments.repository import get_many as get_departments
from app.modules.minor_contracts import repository
from app.modules.minor_contracts.schemas import (
    MinorContractResponse,
    MinorContractUpdate,
    PagedMinorsResponse,
)
from app.modules.users.dependencies import get_request_context
from app.modules.users.service import RequestContext

router = APIRouter(tags=["minor-contracts"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
ContextDep = Annotated[RequestContext, Depends(get_request_context)]
ReadDep = Annotated[authz.AuthzContext, Depends(authz.Authorize("minor_contracts:read"))]
ResourceId = Annotated[int, Path(ge=1)]


def _parse_sort(sort: str) -> tuple[str, bool]:
    descending = sort.startswith("-")
    field = sort.removeprefix("-")
    if field not in repository.SORTABLE_FIELDS:
        raise Problem(422, "Camp d'ordenació no admès", "validation")
    return field, descending


@router.get("/minor-contracts", operation_id="listMinorContracts")
async def list_minor_contracts(
    session: SessionDep,
    authz_ctx: ReadDep,
    ctx: ContextDep,
    page_size: Annotated[int, Query(alias="page[size]", ge=1, le=500)] = 50,
    page_cursor: Annotated[str | None, Query(alias="page[cursor]")] = None,
    view: Annotated[str, Query(pattern=r"^(user|all|dept:[0-9]{1,10})$")] = "user",
    q: Annotated[str | None, Query(max_length=200)] = None,
    sort: str = "-award_date",
    fiscal_year: Annotated[int | None, Query(alias="filter[fiscal_year]")] = None,
    contract_type: Annotated[str | None, Query(alias="filter[contract_type]")] = None,
    department_id: Annotated[int | None, Query(alias="filter[department_id]")] = None,
    unassigned: Annotated[bool | None, Query(alias="filter[unassigned]")] = None,
    settled: Annotated[bool | None, Query(alias="filter[settled]")] = None,
) -> PagedMinorsResponse:
    sort_field, descending = _parse_sort(sort)
    scope = await authz.resolve_view_scope(session, authz_ctx.user, view, ctx)
    minors, total, next_cursor = await repository.list_minors(
        session,
        scope=scope,
        filters={
            "q": q,
            "fiscal_year": fiscal_year,
            "contract_type": contract_type,
            "department_id": department_id,
            "unassigned": unassigned,
            "settled": settled,
        },
        sort_field=sort_field,
        descending=descending,
        page_size=page_size,
        cursor=page_cursor,
    )
    return PagedMinorsResponse(
        data=[MinorContractResponse.from_minor(m) for m in minors],
        meta=PageMeta(total=total, next_cursor=next_cursor),
    )


@router.get("/minor-contracts/{id}", operation_id="getMinorContract")
async def get_minor_contract(
    id: ResourceId, session: SessionDep, authz_ctx: ReadDep
) -> MinorContractResponse:
    minor = await repository.get_visible_minor(session, id, authz_ctx.scope)
    if minor is None:
        raise Problem(404, "Contracte menor no trobat", "not-found")
    return MinorContractResponse.from_minor(minor)


@router.patch("/minor-contracts/{id}", operation_id="updateMinorContract")
async def update_minor_contract(
    id: ResourceId,
    body: MinorContractUpdate,
    session: SessionDep,
    authz_ctx: Annotated[authz.AuthzContext, Depends(authz.Authorize("minor_contracts:update"))],
    ctx: ContextDep,
) -> MinorContractResponse:
    minor = await repository.get_visible_minor(session, id, authz_ctx.scope)
    if minor is None:
        raise Problem(404, "Contracte menor no trobat", "not-found")

    changes = body.model_dump(exclude_unset=True)
    changed: list[str] = []
    if "department_ids" in changes:
        ids = changes.pop("department_ids") or []
        departments = await get_departments(session, ids)
        if len(departments) != len(set(ids)):
            raise Problem(422, "Algun departament no existeix", "validation")
        minor.departments = departments
        changed.append("department_ids")
    if "internal_status" in changes:
        new_status = changes.pop("internal_status")
        if new_status != minor.internal_status:
            minor.internal_status = InternalStatus(new_status)
            changed.append("internal_status")

    if changed:
        await session.flush()
        await record_audit(
            session,
            actor_type=AuditActorType.USER,
            action="minor_contracts.update",
            success=True,
            actor_id=authz_ctx.user.id,
            resource_type="minor_contract",
            resource_id=str(minor.id),
            ip=ctx.ip,
            user_agent=ctx.user_agent,
            trace_id=ctx.trace_id,
            details={"changed": sorted(changed)},
        )
    await session.commit()
    return MinorContractResponse.from_minor(minor)
