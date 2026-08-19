"""Consulta i verificació d'audit_log (specs/audit-log-ui.md).

Només lectura: la taula és append-only i cap endpoint hi escriu res
(tret de l'entrada d'auditoria de la mateixa verificació).
"""

import hashlib
import json
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import ColumnElement

from app.core import authz
from app.core.db import get_session
from app.core.pagination import PageMeta, decode_cursor, encode_cursor, keyset_condition
from app.modules.audit.models import AuditActorType, AuditLogEntry
from app.modules.audit.service import record_audit
from app.modules.users.dependencies import get_request_context
from app.modules.users.models import User
from app.modules.users.service import RequestContext

router = APIRouter(tags=["audit"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
ContextDep = Annotated[RequestContext, Depends(get_request_context)]
ReadDep = Annotated[authz.AuthzContext, Depends(authz.Authorize("audit_log:read"))]


class AuditEntryResponse(BaseModel):
    id: int
    occurred_at: datetime
    actor_type: AuditActorType
    actor_id: int | None
    actor_name: str | None
    action: str
    resource_type: str | None
    resource_id: str | None
    ip: str | None
    trace_id: str | None
    details: dict[str, Any] | None
    success: bool


class PagedAuditResponse(BaseModel):
    data: list[AuditEntryResponse]
    meta: PageMeta


@router.get("/audit-log", operation_id="listAuditLog")
async def list_audit_log(
    session: SessionDep,
    _authz: ReadDep,
    page_size: Annotated[int, Query(alias="page[size]", ge=1, le=200)] = 50,
    page_cursor: Annotated[str | None, Query(alias="page[cursor]")] = None,
    action: Annotated[str | None, Query(alias="filter[action]", max_length=100)] = None,
    actor_type: Annotated[AuditActorType | None, Query(alias="filter[actor_type]")] = None,
    actor_id: Annotated[int | None, Query(alias="filter[actor_id]")] = None,
    success: Annotated[bool | None, Query(alias="filter[success]")] = None,
    resource_type: Annotated[
        str | None, Query(alias="filter[resource_type]", max_length=100)
    ] = None,
    resource_id: Annotated[str | None, Query(alias="filter[resource_id]", max_length=100)] = None,
    trace_id: Annotated[str | None, Query(alias="filter[trace_id]", max_length=100)] = None,
    occurred_from: Annotated[datetime | None, Query(alias="filter[from]")] = None,
    occurred_to: Annotated[datetime | None, Query(alias="filter[to]")] = None,
) -> PagedAuditResponse:
    conditions: list[ColumnElement[bool]] = []
    if action:
        # Prefix, mai LIKE amb entrada crua: escapem els comodins.
        escaped = action.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        conditions.append(AuditLogEntry.action.like(escaped + "%", escape="\\"))
    if actor_type is not None:
        conditions.append(AuditLogEntry.actor_type == actor_type)
    if actor_id is not None:
        conditions.append(AuditLogEntry.actor_id == actor_id)
    if success is not None:
        conditions.append(AuditLogEntry.success == success)
    if resource_type:
        conditions.append(AuditLogEntry.resource_type == resource_type)
    if resource_id:
        conditions.append(AuditLogEntry.resource_id == resource_id)
    if trace_id:
        conditions.append(AuditLogEntry.trace_id == trace_id)
    if occurred_from is not None:
        conditions.append(AuditLogEntry.occurred_at >= occurred_from)
    if occurred_to is not None:
        conditions.append(AuditLogEntry.occurred_at <= occurred_to)

    total = (
        await session.execute(select(func.count()).select_from(AuditLogEntry).where(*conditions))
    ).scalar_one()

    query = (
        select(AuditLogEntry, User.name)
        .join(
            User,
            (AuditLogEntry.actor_id == User.id) & (AuditLogEntry.actor_type == AuditActorType.USER),
            isouter=True,
        )
        .where(*conditions)
        .order_by(AuditLogEntry.id.desc())
        .limit(page_size + 1)
    )
    if page_cursor:
        _, last_id = decode_cursor(page_cursor)
        query = query.where(
            keyset_condition(AuditLogEntry.id, AuditLogEntry.id, last_id, last_id, descending=True)
        )

    rows = (await session.execute(query)).all()
    has_more = len(rows) > page_size
    rows = rows[:page_size]
    next_cursor = encode_cursor([rows[-1][0].id, rows[-1][0].id]) if has_more and rows else None
    return PagedAuditResponse(
        data=[
            AuditEntryResponse(
                id=e.id,
                occurred_at=e.occurred_at,
                actor_type=e.actor_type,
                actor_id=e.actor_id,
                actor_name=name,
                action=e.action,
                resource_type=e.resource_type,
                resource_id=e.resource_id,
                ip=str(e.ip) if e.ip is not None else None,
                trace_id=e.trace_id,
                details=e.details,
                success=e.success,
            )
            for e, name in rows
        ],
        meta=PageMeta(total=total, next_cursor=next_cursor),
    )


def _canonical_payload(entry: AuditLogEntry) -> str:
    """Reconstrueix el payload EXACTAMENT com record_audit el va signar."""
    return json.dumps(
        {
            "occurred_at": entry.occurred_at.isoformat(),
            "actor_type": entry.actor_type.value,
            "actor_id": entry.actor_id,
            "action": entry.action,
            "resource_type": entry.resource_type,
            "resource_id": entry.resource_id,
            "ip": str(entry.ip) if entry.ip is not None else None,
            "trace_id": entry.trace_id,
            "details": entry.details,
            "success": entry.success,
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def check_chain_entry(entry: AuditLogEntry, prev_hash: str | None, *, is_first: bool) -> str | None:
    """Comprova una entrada contra l'anterior; retorna el defecte o None.

    La primera fila present fa d'àncora (les anteriors al desplegament del
    trigger poden no existir): el seu prev_hash s'accepta tal qual.
    """
    if not is_first and entry.prev_hash != prev_hash:
        return "enllaç prev_hash trencat"
    anchor = entry.prev_hash if is_first else prev_hash
    expected = hashlib.sha256(f"{anchor or ''}|{_canonical_payload(entry)}".encode()).hexdigest()
    if entry.entry_hash != expected:
        return "entry_hash no coincideix amb el contingut"
    return None


@router.post("/audit-log/actions/verify", operation_id="verifyAuditChain")
async def verify_audit_chain(
    session: SessionDep, authz_ctx: ReadDep, ctx: ContextDep
) -> dict[str, Any]:
    """Verifica la cadena de hash sencera (només lectura)."""
    checked = 0
    first_broken: int | None = None
    detail: str | None = None
    prev_hash: str | None = None
    stream = await session.stream(
        select(AuditLogEntry).order_by(AuditLogEntry.id).execution_options(yield_per=500)
    )
    async for (entry,) in stream:
        defect = check_chain_entry(entry, prev_hash, is_first=checked == 0)
        if defect is not None:
            first_broken, detail = entry.id, defect
            break
        prev_hash = entry.entry_hash
        checked += 1
    await stream.close()  # si hem sortit amb break, el cursor seguiria obert

    status = "ok" if first_broken is None else "broken"
    await record_audit(
        session,
        actor_type=AuditActorType.USER,
        action="audit.verify_chain",
        success=first_broken is None,
        actor_id=authz_ctx.user.id,
        resource_type="audit_log",
        resource_id=str(first_broken) if first_broken else None,
        ip=ctx.ip,
        user_agent=ctx.user_agent,
        trace_id=ctx.trace_id,
        details={"checked": checked},
    )
    await session.commit()
    result: dict[str, Any] = {"status": status, "checked": checked}
    if first_broken is not None:
        result["first_broken_id"] = first_broken
        result["detail"] = detail
    return result
