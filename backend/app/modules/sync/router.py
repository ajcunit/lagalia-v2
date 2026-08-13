"""Historial i llançament de sincronitzacions (specs/sync-admin.md).

El llançament encua jobs existents: la crida externa viu al worker,
mai dins de la request (06 §2). El camp trigger es determina aquí,
mai ve del client.
"""

from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import authz
from app.core.db import get_session
from app.core.pagination import PageMeta, decode_cursor, encode_cursor, keyset_condition
from app.core.problems import Problem
from app.integrations.models import SyncItemLog, SyncKind, SyncRun, SyncStatus, SyncTrigger
from app.jobs.service import enqueue_job
from app.modules.audit.models import AuditActorType
from app.modules.audit.service import record_audit
from app.modules.users.dependencies import get_request_context
from app.modules.users.service import RequestContext

router = APIRouter(tags=["sync"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
ContextDep = Annotated[RequestContext, Depends(get_request_context)]
ReadDep = Annotated[authz.AuthzContext, Depends(authz.Authorize("sync:read"))]
ExecuteDep = Annotated[authz.AuthzContext, Depends(authz.Authorize("sync:execute"))]

# kind públic → job registrat. L'enriquiment massiu és deliberadament l'últim:
# pica un servei extern expedient a expedient.
_KIND_TO_JOB: dict[str, str] = {
    "contracts": "sync.contracts",
    "minor": "sync.minor_contracts",
    "cpv": "sync.cpv",
    "extensions": "sync.extensions",
    "enrichment": "enrich.batch",
}


class SyncRunResponse(BaseModel):
    id: int
    kind: SyncKind
    trigger: SyncTrigger
    status: SyncStatus
    started_at: datetime | None
    finished_at: datetime | None
    new_count: int
    updated_count: int
    unchanged_count: int
    total_source: int | None
    endpoint: str | None
    error_summary: dict[str, Any] | None


class SyncItemResponse(BaseModel):
    id: int
    file_code: str | None
    outcome: str | None
    message: str | None
    created_at: datetime


class PagedRunsResponse(BaseModel):
    data: list[SyncRunResponse]
    meta: PageMeta


class PagedItemsResponse(BaseModel):
    data: list[SyncItemResponse]
    meta: PageMeta


class TriggerRequest(BaseModel):
    kind: Literal["contracts", "minor", "cpv", "extensions", "enrichment"]
    full: bool = False
    limit: Annotated[int | None, Field(ge=1, le=10000)] = None


@router.get("/sync-runs", operation_id="listSyncRuns")
async def list_sync_runs(
    session: SessionDep,
    _authz: ReadDep,
    page_size: Annotated[int, Query(alias="page[size]", ge=1, le=100)] = 25,
    page_cursor: Annotated[str | None, Query(alias="page[cursor]")] = None,
    kind: Annotated[SyncKind | None, Query(alias="filter[kind]")] = None,
    status: Annotated[SyncStatus | None, Query(alias="filter[status]")] = None,
) -> PagedRunsResponse:
    conditions = []
    if kind is not None:
        conditions.append(SyncRun.kind == kind)
    if status is not None:
        conditions.append(SyncRun.status == status)

    total = (
        await session.execute(select(func.count()).select_from(SyncRun).where(*conditions))
    ).scalar_one()

    query = select(SyncRun).where(*conditions).order_by(SyncRun.id.desc()).limit(page_size + 1)
    if page_cursor:
        _, last_id = decode_cursor(page_cursor)
        query = query.where(
            keyset_condition(SyncRun.id, SyncRun.id, last_id, last_id, descending=True)
        )

    runs = list((await session.execute(query)).scalars())
    has_more = len(runs) > page_size
    runs = runs[:page_size]
    next_cursor = encode_cursor([runs[-1].id, runs[-1].id]) if has_more and runs else None
    return PagedRunsResponse(
        data=[SyncRunResponse.model_validate(r, from_attributes=True) for r in runs],
        meta=PageMeta(total=total, next_cursor=next_cursor),
    )


@router.get("/sync-runs/{id}/items", operation_id="listSyncRunItems")
async def list_sync_run_items(
    id: int,
    session: SessionDep,
    _authz: ReadDep,
    page_size: Annotated[int, Query(alias="page[size]", ge=1, le=200)] = 50,
    page_cursor: Annotated[str | None, Query(alias="page[cursor]")] = None,
) -> PagedItemsResponse:
    if await session.get(SyncRun, id) is None:
        raise Problem(404, "Sincronització desconeguda", "not-found")

    conditions = [SyncItemLog.sync_run_id == id]
    total = (
        await session.execute(select(func.count()).select_from(SyncItemLog).where(*conditions))
    ).scalar_one()

    query = (
        select(SyncItemLog).where(*conditions).order_by(SyncItemLog.id.desc()).limit(page_size + 1)
    )
    if page_cursor:
        _, last_id = decode_cursor(page_cursor)
        query = query.where(
            keyset_condition(SyncItemLog.id, SyncItemLog.id, last_id, last_id, descending=True)
        )

    items = list((await session.execute(query)).scalars())
    has_more = len(items) > page_size
    items = items[:page_size]
    next_cursor = encode_cursor([items[-1].id, items[-1].id]) if has_more and items else None
    return PagedItemsResponse(
        data=[SyncItemResponse.model_validate(i, from_attributes=True) for i in items],
        meta=PageMeta(total=total, next_cursor=next_cursor),
    )


@router.post("/sync-runs/actions/trigger", operation_id="triggerSync", status_code=202)
async def trigger_sync(
    body: TriggerRequest, session: SessionDep, authz_ctx: ExecuteDep, ctx: ContextDep
) -> dict[str, Any]:
    job_type = _KIND_TO_JOB[body.kind]
    machine = authz.is_machine(authz_ctx.user)
    trigger = SyncTrigger.API if machine else SyncTrigger.MANUAL
    payload: dict[str, Any] = {"trigger": trigger.value}
    if body.kind == "enrichment":
        payload["force"] = body.full
        if body.limit is not None:
            payload["limit"] = body.limit
    else:
        payload["full"] = body.full

    job = await enqueue_job(
        session,
        job_type=job_type,
        payload=payload,
        created_by=authz_ctx.user.id or None,
        dedup_key=f"trigger:{job_type}",
    )
    await record_audit(
        session,
        actor_type=AuditActorType.AGENT if machine else AuditActorType.USER,
        action="sync.trigger",
        success=True,
        actor_id=authz_ctx.user.id or None,
        resource_type="sync",
        resource_id=body.kind,
        ip=ctx.ip,
        user_agent=ctx.user_agent,
        trace_id=ctx.trace_id,
        details={"job_type": job_type, "full": body.full, "limit": body.limit},
    )
    await session.commit()
    return {"job_id": str(job.id), "job_type": job_type}
