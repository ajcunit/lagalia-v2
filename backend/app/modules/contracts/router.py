"""Endpoints de contractes. Prims: abast i regles als serveis/repositori."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import authz
from app.core.db import get_session
from app.core.pagination import PageMeta
from app.core.problems import Problem
from app.modules.contracts import repository, service
from app.modules.contracts.models import InternalStatus
from app.modules.contracts.schemas import (
    AwardCriterionResponse,
    CommitteeMemberResponse,
    ContractCreate,
    ContractDetail,
    ContractSummary,
    ContractUpdate,
    ExtensionResponse,
    HistoryEntryResponse,
    ModificationResponse,
    PagedContractsResponse,
    PagedHistoryResponse,
    PhaseDocumentResponse,
)
from app.modules.users.dependencies import (
    CurrentSession,
    get_current_session,
    get_request_context,
)
from app.modules.users.service import RequestContext

router = APIRouter(tags=["contracts"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
ContextDep = Annotated[RequestContext, Depends(get_request_context)]
ReadDep = Annotated[authz.AuthzContext, Depends(authz.Authorize("contracts:read"))]
ResourceId = Annotated[int, Path(ge=1)]


def _parse_sort(sort: str) -> tuple[str, bool]:
    descending = sort.startswith("-")
    field = sort.removeprefix("-")
    if field not in repository.SORTABLE_FIELDS:
        raise Problem(422, "Camp d'ordenació no admès", "validation")
    return field, descending


async def _effective_scope(
    session: AsyncSession, authz_ctx: authz.AuthzContext, view: str, ctx: RequestContext
) -> authz.ScopeInfo:
    return await authz.resolve_view_scope(session, authz_ctx.user, view, ctx)


@router.get("/contracts", operation_id="listContracts")
async def list_contracts(
    session: SessionDep,
    authz_ctx: ReadDep,
    ctx: ContextDep,
    page_size: Annotated[int, Query(alias="page[size]", ge=1, le=500)] = 50,
    page_cursor: Annotated[str | None, Query(alias="page[cursor]")] = None,
    view: Annotated[str, Query(pattern="^(user|all)$")] = "user",
    q: Annotated[str | None, Query(max_length=200)] = None,
    sort: str = "-published_at",
    department_id: Annotated[int | None, Query(alias="filter[department_id]")] = None,
    unassigned: Annotated[bool | None, Query(alias="filter[unassigned]")] = None,
    contract_type: Annotated[str | None, Query(alias="filter[contract_type]")] = None,
    status: Annotated[str | None, Query(alias="filter[status]")] = None,
    internal_status: Annotated[
        InternalStatus | None, Query(alias="filter[internal_status]")
    ] = None,
    expiry_warning: Annotated[bool | None, Query(alias="filter[expiry_warning]")] = None,
    possibly_finished: Annotated[bool | None, Query(alias="filter[possibly_finished]")] = None,
    year: Annotated[int | None, Query(alias="filter[year]")] = None,
    contractor_id: Annotated[int | None, Query(alias="filter[contractor_id]")] = None,
) -> PagedContractsResponse:
    sort_field, descending = _parse_sort(sort)
    scope = await _effective_scope(session, authz_ctx, view, ctx)
    contracts, total, next_cursor = await repository.list_contracts(
        session,
        scope=scope,
        user_id=authz_ctx.user.id,
        filters={
            "q": q,
            "department_id": department_id,
            "unassigned": unassigned,
            "contract_type": contract_type,
            "status": status,
            "internal_status": internal_status,
            "expiry_warning": expiry_warning,
            "possibly_finished": possibly_finished,
            "year": year,
            "contractor_id": contractor_id,
        },
        sort_field=sort_field,
        descending=descending,
        page_size=page_size,
        cursor=page_cursor,
    )
    return PagedContractsResponse(
        data=[ContractSummary.from_contract(c) for c in contracts],
        meta=PageMeta(total=total, next_cursor=next_cursor),
    )


@router.post("/contracts", operation_id="createContract", status_code=201)
async def create_contract(
    body: ContractCreate,
    session: SessionDep,
    authz_ctx: Annotated[authz.AuthzContext, Depends(authz.Authorize("contracts:create"))],
    ctx: ContextDep,
) -> ContractDetail:
    contract = await service.create_contract(session, body, authz_ctx.user, ctx)
    contract = await service.get_scoped_contract(
        session, contract.id, authz_ctx.user, authz.ScopeInfo(type="all")
    )
    return ContractDetail.build(contract, [], await repository.counters(session, contract.id))


@router.get("/contracts/{id}", operation_id="getContract")
async def get_contract(
    id: ResourceId, session: SessionDep, authz_ctx: ReadDep, ctx: ContextDep
) -> ContractDetail:
    contract = await service.get_scoped_contract(session, id, authz_ctx.user, authz_ctx.scope)
    return ContractDetail.build(
        contract,
        await repository.siblings(session, contract),
        await repository.counters(session, contract.id),
    )


@router.patch("/contracts/{id}", operation_id="updateContract")
async def update_contract(
    id: ResourceId,
    body: ContractUpdate,
    session: SessionDep,
    current: Annotated[CurrentSession, Depends(get_current_session)],
    ctx: ContextDep,
) -> ContractDetail:
    contract = await service.update_contract(session, id, body, current.user, ctx)
    return ContractDetail.build(
        contract,
        await repository.siblings(session, contract),
        await repository.counters(session, contract.id),
    )


@router.get("/contracts/{id}/history", operation_id="getContractHistory")
async def get_contract_history(
    id: ResourceId,
    session: SessionDep,
    authz_ctx: ReadDep,
    page_size: Annotated[int, Query(alias="page[size]", ge=1, le=500)] = 50,
    page_cursor: Annotated[str | None, Query(alias="page[cursor]")] = None,
) -> PagedHistoryResponse:
    await service.get_scoped_contract(session, id, authz_ctx.user, authz_ctx.scope)
    entries, total, next_cursor = await repository.history_page(
        session, id, page_size=page_size, cursor=page_cursor
    )
    return PagedHistoryResponse(
        data=[HistoryEntryResponse.from_entry(e) for e in entries],
        meta=PageMeta(total=total, next_cursor=next_cursor),
    )


@router.get("/contracts/{id}/extensions", operation_id="getContractExtensions")
async def get_contract_extensions(
    id: ResourceId, session: SessionDep, authz_ctx: ReadDep
) -> dict[str, list[ExtensionResponse]]:
    await service.get_scoped_contract(session, id, authz_ctx.user, authz_ctx.scope)
    extensions = await repository.extensions_of(session, id)
    return {"data": [ExtensionResponse.from_extension(e) for e in extensions]}


@router.get("/contracts/{id}/modifications", operation_id="getContractModifications")
async def get_contract_modifications(
    id: ResourceId, session: SessionDep, authz_ctx: ReadDep
) -> dict[str, list[ModificationResponse]]:
    await service.get_scoped_contract(session, id, authz_ctx.user, authz_ctx.scope)
    modifications = await repository.modifications_of(session, id)
    return {"data": [ModificationResponse.from_modification(m) for m in modifications]}


@router.get("/contracts/{id}/criteria", operation_id="getContractCriteria")
async def get_contract_criteria(
    id: ResourceId, session: SessionDep, authz_ctx: ReadDep
) -> dict[str, list[AwardCriterionResponse]]:
    await service.get_scoped_contract(session, id, authz_ctx.user, authz_ctx.scope)
    criteria = await repository.criteria_of(session, id)
    return {"data": [AwardCriterionResponse.from_criterion(c) for c in criteria]}


@router.get("/contracts/{id}/committee", operation_id="getContractCommittee")
async def get_contract_committee(
    id: ResourceId, session: SessionDep, authz_ctx: ReadDep
) -> dict[str, list[CommitteeMemberResponse]]:
    await service.get_scoped_contract(session, id, authz_ctx.user, authz_ctx.scope)
    members = await repository.committee_of(session, id)
    return {"data": [CommitteeMemberResponse.from_member(m) for m in members]}


@router.get("/contracts/{id}/documents", operation_id="getContractDocuments")
async def get_contract_documents(
    id: ResourceId, session: SessionDep, authz_ctx: ReadDep
) -> dict[str, list[PhaseDocumentResponse]]:
    await service.get_scoped_contract(session, id, authz_ctx.user, authz_ctx.scope)
    documents = await repository.documents_of(session, id)
    return {"data": [PhaseDocumentResponse.from_document(d) for d in documents]}
