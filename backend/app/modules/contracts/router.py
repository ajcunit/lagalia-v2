"""Endpoints de contractes. Prims: abast i regles als serveis/repositori."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import authz
from app.core.db import get_session
from app.core.pagination import PageMeta
from app.core.problems import Problem
from app.core.storage import get_storage
from app.jobs import ephemeral
from app.jobs.models import Job, JobStatus
from app.jobs.schemas import JobResponse
from app.modules.audit.models import AuditActorType
from app.modules.audit.service import record_audit
from app.modules.contracts import repository, service
from app.modules.contracts.models import InternalStatus
from app.modules.contracts.schemas import (
    AwardCriterionResponse,
    BulkAssignRequest,
    BulkAssignResult,
    CommitteeMemberResponse,
    ContractCreate,
    ContractDetail,
    ContractFacets,
    ContractStats,
    ContractSummary,
    ContractUpdate,
    ExportRequest,
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
    view: Annotated[str, Query(pattern=r"^(user|all|dept:[0-9]{1,10})$")] = "user",
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


@router.get("/contracts/stats", operation_id="getContractsStats")
async def get_contracts_stats(
    session: SessionDep,
    authz_ctx: ReadDep,
    ctx: ContextDep,
    view: Annotated[str, Query(pattern=r"^(user|all|dept:[0-9]{1,10})$")] = "user",
    year: Annotated[int | None, Query(alias="filter[year]")] = None,
    amount_min: Annotated[float | None, Query(alias="filter[amount_min]", ge=0)] = None,
    amount_max: Annotated[float | None, Query(alias="filter[amount_max]", ge=0)] = None,
) -> ContractStats:
    scope = await _effective_scope(session, authz_ctx, view, ctx)
    data = await repository.stats(
        session,
        scope=scope,
        user_id=authz_ctx.user.id,
        year=year,
        amount_min=amount_min,
        amount_max=amount_max,
    )
    return ContractStats.model_validate(data)


@router.get("/contracts/facets", operation_id="getContractsFacets")
async def get_contracts_facets(
    session: SessionDep,
    authz_ctx: ReadDep,
    ctx: ContextDep,
    view: Annotated[str, Query(pattern=r"^(user|all|dept:[0-9]{1,10})$")] = "user",
) -> ContractFacets:
    scope = await _effective_scope(session, authz_ctx, view, ctx)
    data = await repository.facets(session, scope=scope, user_id=authz_ctx.user.id)
    return ContractFacets.model_validate(data)


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


async def _detail(session: AsyncSession, contract: Any) -> ContractDetail:
    return ContractDetail.build(
        contract,
        await repository.siblings(session, contract),
        await repository.counters(session, contract.id),
    )


@router.post("/contracts/{id}/actions/finish", operation_id="finishContract")
async def finish_contract(
    id: ResourceId,
    session: SessionDep,
    current: Annotated[CurrentSession, Depends(get_current_session)],
    ctx: ContextDep,
) -> ContractDetail:
    contract = await service.finish_contract(session, id, current.user, ctx)
    return await _detail(session, contract)


@router.post("/contracts/{id}/actions/dismiss-expiry", operation_id="dismissContractExpiry")
async def dismiss_contract_expiry(
    id: ResourceId,
    session: SessionDep,
    current: Annotated[CurrentSession, Depends(get_current_session)],
    ctx: ContextDep,
) -> ContractDetail:
    contract = await service.dismiss_expiry(session, id, current.user, ctx)
    return await _detail(session, contract)


@router.post("/contracts/{id}/actions/enrich", operation_id="enrichContract", status_code=202)
async def enrich_contract(
    id: ResourceId,
    session: SessionDep,
    current: Annotated[CurrentSession, Depends(get_current_session)],
    ctx: ContextDep,
) -> JobResponse:
    job = await service.enqueue_enrichment(session, id, current.user, ctx)
    return JobResponse.from_job(job)


@router.post("/contracts/exports", operation_id="createContractsExport", status_code=202)
async def create_contracts_export(
    body: ExportRequest,
    session: SessionDep,
    current: Annotated[CurrentSession, Depends(get_current_session)],
    ctx: ContextDep,
) -> JobResponse:
    job = await service.enqueue_export(session, body, current.user, ctx)
    return JobResponse.from_job(job)


@router.get("/contracts/exports/{id}/download", operation_id="downloadContractsExport")
async def download_contracts_export(
    id: uuid.UUID,
    session: SessionDep,
    ctx: ContextDep,
    token: Annotated[str, Query(min_length=16, max_length=128)],
) -> Response:
    """Sense capçalera d'autenticació: el token efímer d'un sol ús és l'autorització."""
    grant = await ephemeral.consume_token(token)
    if grant is None or grant.purpose != "download" or grant.resource != str(id):
        raise Problem(401, "Token de descàrrega invàlid o ja utilitzat", "unauthorized")

    job = await session.get(Job, id)
    if job is None or job.type != "export.contracts":
        raise Problem(404, "Exportació no trobada", "not-found")
    if job.status != JobStatus.SUCCESS or not job.result:
        raise Problem(409, "L'exportació encara no està disponible", "conflict")

    result: dict[str, Any] = dict(job.result)
    content = await get_storage().get(str(result["storage_key"]))
    await record_audit(
        session,
        actor_type=AuditActorType.USER,
        action="contracts.export_download",
        success=True,
        actor_id=grant.user_id,
        resource_type="job",
        resource_id=str(id),
        ip=ctx.ip,
        user_agent=ctx.user_agent,
        trace_id=ctx.trace_id,
    )
    await session.commit()
    return Response(
        content=content,
        media_type=str(result.get("content_type") or "application/octet-stream"),
        headers={"Content-Disposition": f'attachment; filename="{result["filename"]}"'},
    )


@router.post("/contracts/bulk/assign-departments", operation_id="bulkAssignDepartments")
async def bulk_assign_departments(
    body: BulkAssignRequest,
    session: SessionDep,
    current: Annotated[CurrentSession, Depends(get_current_session)],
    ctx: ContextDep,
) -> BulkAssignResult:
    result = await service.bulk_assign_departments(session, body, current.user, ctx)
    return BulkAssignResult(**result)


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


@router.get("/contracts/{id}/executions", operation_id="getContractExecutions")
async def get_contract_executions(
    id: ResourceId, session: SessionDep, authz_ctx: ReadDep
) -> dict[str, list[dict[str, Any]]]:
    """Actuacions de la fase d'execució (specs/execution-sync.md): totes les
    files de l'expedient (per file_code, tots els lots), més recents primer."""
    contract = await service.get_scoped_contract(session, id, authz_ctx.user, authz_ctx.scope)
    from sqlalchemy import text as sql_text

    rows = (
        await session.execute(
            sql_text(
                "SELECT id, lot, action_type, action_name, date, end_date, amount, "
                "contractor_name, contractor_tax_id, observations, url_json, "
                "suposit_habilitant, documents "
                "FROM contract_executions WHERE file_code = :f "
                "ORDER BY date DESC NULLS LAST, id DESC"
            ),
            {"f": contract.file_code},
        )
    ).mappings().all()
    return {"data": [dict(row) for row in rows]}
