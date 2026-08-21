"""Endpoints d'adjudicataris: rànquing, fitxa i duplicats.

La ruta literal /contractors/duplicates es registra ABANS de
/contractors/{id} perquè no col·lisionin.
"""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import authz
from app.core.db import get_session
from app.core.pagination import PageMeta
from app.core.problems import Problem
from app.modules.audit.models import AuditActorType
from app.modules.audit.service import record_audit
from app.modules.contractors import repository, service
from app.modules.contractors.models import ContractorDuplicate, ContractorDuplicateStatus
from app.modules.contractors.schemas import (
    ContractorDuplicateGroup,
    ContractorDuplicateResponse,
    ContractorMinorTotals,
    ContractorProfile,
    DuplicateResolveRequest,
    GroupResolveRequest,
    GroupResolveResult,
    PagedDuplicateGroupsResponse,
    PagedDuplicatesResponse,
    PagedRankingResponse,
    ranking_from_dict,
)
from app.modules.users.dependencies import get_request_context
from app.modules.users.service import RequestContext

router = APIRouter(tags=["contractors"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
ContextDep = Annotated[RequestContext, Depends(get_request_context)]
ReadDep = Annotated[authz.AuthzContext, Depends(authz.Authorize("contracts:read"))]
ManageDep = Annotated[authz.AuthzContext, Depends(authz.Authorize("duplicates:manage"))]


@router.get("/contractors", operation_id="listContractors")
async def list_contractors(
    session: SessionDep,
    _authz: ReadDep,
    page_size: Annotated[int, Query(alias="page[size]", ge=1, le=500)] = 50,
    page_cursor: Annotated[str | None, Query(alias="page[cursor]")] = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
    sort: str = "-total_amount",
) -> PagedRankingResponse:
    descending = sort.startswith("-")
    sort_key = sort.removeprefix("-")
    if sort_key not in repository.RANKING_SORT_KEYS:
        raise Problem(422, "Camp d'ordenació no admès", "validation")
    rows, total, next_cursor = await repository.ranking(
        session,
        q=q,
        sort_key=sort_key,
        descending=descending,
        page_size=page_size,
        cursor=page_cursor,
    )
    return PagedRankingResponse(
        data=[ranking_from_dict(r) for r in rows],
        meta=PageMeta(total=total, next_cursor=next_cursor),
    )


async def _duplicate_response(
    session: AsyncSession, duplicate: ContractorDuplicate
) -> ContractorDuplicateResponse:
    # Viu si el contractista encara existeix; instantània si la fusió se
    # l'ha endut (l'històric de resolts no desapareix mai).
    first = (
        await repository.ranking_by_id(session, duplicate.contractor_id_1)
        if duplicate.contractor_id_1 is not None
        else None
    ) or duplicate.snapshot_1
    second = (
        await repository.ranking_by_id(session, duplicate.contractor_id_2)
        if duplicate.contractor_id_2 is not None
        else None
    ) or duplicate.snapshot_2
    if first is None or second is None:
        raise Problem(404, "Parell de duplicats no trobat", "not-found")
    return ContractorDuplicateResponse(
        id=duplicate.id,
        status=duplicate.status.value,
        contractor_1=ranking_from_dict(first),
        contractor_2=ranking_from_dict(second),
        resolved_by=duplicate.resolved_by,
        resolved_at=duplicate.resolved_at,
        created_at=duplicate.created_at,
    )


@router.get("/contractors/duplicates", operation_id="listContractorDuplicates")
async def list_contractor_duplicates(
    session: SessionDep,
    _authz: ManageDep,
    page_size: Annotated[int, Query(alias="page[size]", ge=1, le=500)] = 50,
    page_cursor: Annotated[str | None, Query(alias="page[cursor]")] = None,
    status: Annotated[ContractorDuplicateStatus, Query()] = (ContractorDuplicateStatus.PENDING),
) -> PagedDuplicatesResponse:
    duplicates, total, next_cursor = await repository.duplicates_page(
        session, status=status, page_size=page_size, cursor=page_cursor
    )
    data = [await _duplicate_response(session, d) for d in duplicates]
    return PagedDuplicatesResponse(data=data, meta=PageMeta(total=total, next_cursor=next_cursor))


@router.get("/contractors/duplicates/groups", operation_id="listContractorDuplicateGroups")
async def list_contractor_duplicate_groups(
    session: SessionDep,
    _authz: ManageDep,
    page_size: Annotated[int, Query(alias="page[size]", ge=1, le=100)] = 25,
    page_cursor: Annotated[str | None, Query(alias="page[cursor]")] = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
) -> PagedDuplicateGroupsResponse:
    groups, total, next_cursor = await repository.duplicate_groups(
        session, page_size=page_size, cursor=page_cursor, q=q
    )
    return PagedDuplicateGroupsResponse(
        data=[ContractorDuplicateGroup.model_validate(g) for g in groups],
        meta=PageMeta(total=total, next_cursor=next_cursor),
    )


@router.post(
    "/contractors/duplicates/groups/resolve", operation_id="resolveContractorDuplicateGroup"
)
async def resolve_contractor_duplicate_group(
    body: GroupResolveRequest,
    session: SessionDep,
    authz_ctx: ManageDep,
    ctx: ContextDep,
) -> GroupResolveResult:
    try:
        result = await service.resolve_duplicate_group(
            session,
            tax_id=body.tax_id,
            action=body.action,
            canonical_id=body.canonical_id,
            resolved_by=authz_ctx.user.id,
        )
    except ValueError as exc:
        raise Problem(422, str(exc), "validation") from None
    await record_audit(
        session,
        actor_type=AuditActorType.USER,
        action="contractors.merge_group" if body.action == "merge" else "contractors.reject_group",
        success=True,
        actor_id=authz_ctx.user.id,
        resource_type="contractor_group",
        resource_id=body.tax_id,
        ip=ctx.ip,
        user_agent=ctx.user_agent,
        trace_id=ctx.trace_id,
        details={"canonical_id": body.canonical_id, **result},
    )
    await session.commit()
    return GroupResolveResult(**result)


@router.post(
    "/contractors/duplicates/{id}/actions/resolve",
    operation_id="resolveContractorDuplicate",
)
async def resolve_contractor_duplicate(
    id: Annotated[int, Path(ge=1)],
    body: DuplicateResolveRequest,
    session: SessionDep,
    authz_ctx: ManageDep,
    ctx: ContextDep,
) -> ContractorDuplicateResponse:
    duplicate = await session.get(ContractorDuplicate, id)
    if duplicate is None:
        raise Problem(404, "Parell de duplicats no trobat", "not-found")
    if duplicate.status != ContractorDuplicateStatus.PENDING:
        raise Problem(409, "El parell ja està resolt", "conflict")

    now = datetime.now(UTC)
    duplicate.resolved_by = authz_ctx.user.id
    duplicate.resolved_at = now
    # Instantània de cada costat: si després es fusiona el grup, el parell
    # resolt conserva les dades del moment.
    duplicate.snapshot_1 = service.ranking_snapshot(
        await repository.ranking_by_id(session, duplicate.contractor_id_1)
        if duplicate.contractor_id_1 is not None
        else None
    )
    duplicate.snapshot_2 = service.ranking_snapshot(
        await repository.ranking_by_id(session, duplicate.contractor_id_2)
        if duplicate.contractor_id_2 is not None
        else None
    )

    if body.action == "reject":
        duplicate.status = ContractorDuplicateStatus.REJECTED
        response = await _duplicate_response(session, duplicate)
        await record_audit(
            session,
            actor_type=AuditActorType.USER,
            action="contractors.duplicate_rejected",
            success=True,
            actor_id=authz_ctx.user.id,
            resource_type="contractor_duplicate",
            resource_id=str(duplicate.id),
            ip=ctx.ip,
            user_agent=ctx.user_agent,
            trace_id=ctx.trace_id,
            details={"notes": body.notes} if body.notes else None,
        )
        await session.commit()
        return response

    winner_id = duplicate.contractor_id_1 if body.action == "merge_1" else duplicate.contractor_id_2
    loser_id = duplicate.contractor_id_2 if body.action == "merge_1" else duplicate.contractor_id_1
    if winner_id is None or loser_id is None:
        raise Problem(409, "El parell ja no té els dos contractistes", "conflict")
    duplicate.status = ContractorDuplicateStatus.MERGED
    # Resposta abans de la fusió (que esborra el perdedor); el parell
    # sobreviu amb la instantània presa més amunt (FK SET NULL).
    response = await _duplicate_response(session, duplicate)

    await service.merge_contractors(session, winner_id=winner_id, loser_id=loser_id)
    await record_audit(
        session,
        actor_type=AuditActorType.USER,
        action="contractors.merge",
        success=True,
        actor_id=authz_ctx.user.id,
        resource_type="contractor",
        resource_id=str(winner_id),
        ip=ctx.ip,
        user_agent=ctx.user_agent,
        trace_id=ctx.trace_id,
        details={
            "duplicate_id": id,
            "winner_id": winner_id,
            "loser_id": loser_id,
            "loser_name": response.contractor_2.name
            if body.action == "merge_1"
            else response.contractor_1.name,
            "notes": body.notes,
        },
    )
    await session.commit()
    return response


@router.get("/contractors/{id}", operation_id="getContractor")
async def get_contractor(
    id: Annotated[int, Path(ge=1)], session: SessionDep, _authz: ReadDep
) -> ContractorProfile:
    values = await repository.profile(session, id)
    if values is None:
        raise Problem(404, "Adjudicatari no trobat", "not-found")
    return ContractorProfile(**values)


@router.get("/contractors/{id}/minor-totals", operation_id="getContractorMinorTotals")
async def get_contractor_minor_totals(
    id: Annotated[int, Path(ge=1)], session: SessionDep, _authz: ReadDep
) -> ContractorMinorTotals:
    """Sumes dels contractes menors per exercici i tipus
    (specs/contractor-economic-status.md): agregat de tot l'ens — el límit
    de menors per adjudicatari no entén de departaments."""
    if await repository.profile(session, id) is None:
        raise Problem(404, "Adjudicatari no trobat", "not-found")
    return ContractorMinorTotals.model_validate(
        {"data": await repository.minor_totals(session, id)}
    )
