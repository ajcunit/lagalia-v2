"""Casos d'ús de contractes: llistat/detall dins d'abast, edició per matriu.

Fora d'abast → 404 (mai es revela l'existència). L'edició distingeix
contracts:update (tots els camps) de contracts:update_warning (només
warning_months_override, dins d'abast).
"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import authz
from app.core.problems import Problem
from app.integrations import hub
from app.jobs.models import Job
from app.jobs.service import enqueue_job
from app.modules.audit.models import AuditActorType
from app.modules.audit.service import record_audit
from app.modules.contracts import repository
from app.modules.contracts.models import (
    ChangeType,
    Contract,
    ContractHistoryEntry,
    ContractSource,
)
from app.modules.contracts.schemas import (
    BulkAssignRequest,
    ContractCreate,
    ContractUpdate,
    ExportRequest,
)
from app.modules.departments.repository import get_many as get_departments
from app.modules.users.models import User
from app.modules.users.service import RequestContext
from app.modules.webhooks.service import emit_event, enqueue_dispatch

_WARNING_ONLY_FIELDS = {"warning_months_override"}

FINISHED_STATUS = "Finalitzat"


def _not_found() -> Problem:
    return Problem(404, "Contracte no trobat", "not-found")


async def get_scoped_contract(
    session: AsyncSession,
    contract_id: int,
    user: User,
    scope: authz.ScopeInfo,
) -> Contract:
    contract = await repository.get_visible_contract(session, contract_id, scope, user.id)
    if contract is None:
        raise _not_found()
    return contract


async def update_contract(
    session: AsyncSession,
    contract_id: int,
    data: ContractUpdate,
    user: User,
    ctx: RequestContext,
) -> Contract:
    update_grant = authz.evaluate(user, "contracts:update")
    warning_grant = authz.evaluate(user, "contracts:update_warning")
    if update_grant is None and warning_grant is None:
        await _audit_denied(session, user, contract_id, "contracts:update", ctx)
        raise Problem(403, "Sense permís per editar contractes", "forbidden")

    # L'abast de visibilitat és el del grant més ampli disponible.
    scope = (
        authz.ScopeInfo(type="all")
        if (update_grant and update_grant.access == authz.Access.ALL)
        else authz.scope_for(user)
    )
    contract = await get_scoped_contract(session, contract_id, user, scope)

    changes = data.model_dump(exclude_unset=True)
    if not changes:
        return contract

    if update_grant is None:
        forbidden_fields = set(changes) - _WARNING_ONLY_FIELDS
        if forbidden_fields:
            await _audit_denied(session, user, contract_id, "contracts:update", ctx)
            raise Problem(
                403,
                "Només es pot modificar l'avís de venciment",
                "forbidden",
                detail=f"Camps no permesos: {', '.join(sorted(forbidden_fields))}",
            )

    changed_fields = []
    for field, value in changes.items():
        old = getattr(contract, field)
        if old == value:
            continue
        session.add(
            ContractHistoryEntry(
                contract_id=contract.id,
                field=field,
                old_value=None if old is None else str(old),
                new_value=None if value is None else str(value),
                user_id=user.id,
                change_type=ChangeType.MANUAL,
            )
        )
        setattr(contract, field, value)
        changed_fields.append(field)

    if changed_fields:
        await session.flush()
        await record_audit(
            session,
            actor_type=AuditActorType.USER,
            action="contracts.update",
            success=True,
            actor_id=user.id,
            resource_type="contract",
            resource_id=str(contract.id),
            ip=ctx.ip,
            user_agent=ctx.user_agent,
            trace_id=ctx.trace_id,
            details={"changed": sorted(changed_fields)},
        )
    await session.commit()
    return contract


async def create_contract(
    session: AsyncSession, data: ContractCreate, user: User, ctx: RequestContext
) -> Contract:
    departments = await get_departments(session, data.department_ids)
    if len(departments) != len(set(data.department_ids)):
        raise Problem(422, "Algun departament no existeix", "validation")

    values: dict[str, Any] = data.model_dump(exclude={"department_ids"})
    contract = Contract(**values, source=ContractSource.LOCAL, departments=departments)
    session.add(contract)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise Problem(
            409, "Ja existeix un contracte amb la mateixa clau natural", "conflict"
        ) from None

    await record_audit(
        session,
        actor_type=AuditActorType.USER,
        action="contracts.create",
        success=True,
        actor_id=user.id,
        resource_type="contract",
        resource_id=str(contract.id),
        ip=ctx.ip,
        user_agent=ctx.user_agent,
        trace_id=ctx.trace_id,
    )
    await session.commit()
    return contract


async def _require_alert_grant(
    session: AsyncSession, contract_id: int, user: User, ctx: RequestContext
) -> Contract:
    """contracts:close_alert: MANAGED = només si és responsable del contracte."""
    grant = authz.evaluate(user, "contracts:close_alert")
    if grant is None:
        await _audit_denied(session, user, contract_id, "contracts:close_alert", ctx)
        raise Problem(403, "Sense permís per gestionar alertes", "forbidden")

    # Visibilitat (404 fora d'abast) amb l'abast normal de l'usuari.
    scope = (
        authz.ScopeInfo(type="all") if grant.access == authz.Access.ALL else authz.scope_for(user)
    )
    contract = await get_scoped_contract(session, contract_id, user, scope)

    if grant.access == authz.Access.MANAGED:
        if not await repository.is_manager(session, contract_id, user.id):
            await _audit_denied(session, user, contract_id, "contracts:close_alert", ctx)
            raise Problem(403, "Només el responsable del contracte pot fer-ho", "forbidden")
    return contract


def _history(
    contract: Contract, field: str, old: Any, new: Any, user_id: int
) -> ContractHistoryEntry:
    return ContractHistoryEntry(
        contract_id=contract.id,
        field=field,
        old_value=None if old is None else str(old),
        new_value=None if new is None else str(new),
        user_id=user_id,
        change_type=ChangeType.MANUAL,
    )


async def finish_contract(
    session: AsyncSession, contract_id: int, user: User, ctx: RequestContext
) -> Contract:
    contract = await _require_alert_grant(session, contract_id, user, ctx)
    if contract.status == FINISHED_STATUS:
        raise Problem(409, "El contracte ja està finalitzat", "conflict")

    session.add(_history(contract, "status", contract.status, FINISHED_STATUS, user.id))
    contract.status = FINISHED_STATUS
    contract.expiry_warning = False
    contract.possibly_finished = False
    await session.flush()
    await emit_event(
        session,
        event_type="contract.finished",
        aggregate="contract",
        aggregate_id=contract.id,
        data={"file_code": contract.file_code, "finished_by": user.id},
    )
    await record_audit(
        session,
        actor_type=AuditActorType.USER,
        action="contracts.finish",
        success=True,
        actor_id=user.id,
        resource_type="contract",
        resource_id=str(contract.id),
        ip=ctx.ip,
        user_agent=ctx.user_agent,
        trace_id=ctx.trace_id,
    )
    await session.commit()
    await enqueue_dispatch(session)
    return contract


async def dismiss_expiry(
    session: AsyncSession, contract_id: int, user: User, ctx: RequestContext
) -> Contract:
    contract = await _require_alert_grant(session, contract_id, user, ctx)
    if not contract.expiry_warning and not contract.possibly_finished:
        raise Problem(409, "El contracte no té cap alerta activa", "conflict")

    session.add(_history(contract, "alert_dismissed", None, "dismissed", user.id))
    contract.alert_dismissed_at = datetime.now(UTC)
    contract.alert_dismissed_end_date = contract.calculated_end_date
    contract.expiry_warning = False
    contract.possibly_finished = False
    await session.flush()
    await record_audit(
        session,
        actor_type=AuditActorType.USER,
        action="contracts.dismiss_expiry",
        success=True,
        actor_id=user.id,
        resource_type="contract",
        resource_id=str(contract.id),
        ip=ctx.ip,
        user_agent=ctx.user_agent,
        trace_id=ctx.trace_id,
    )
    await session.commit()
    return contract


async def enqueue_enrichment(
    session: AsyncSession, contract_id: int, user: User, ctx: RequestContext
) -> Job:
    if authz.evaluate(user, "contracts:enrich") is None:
        await _audit_denied(session, user, contract_id, "contracts:enrich", ctx)
        raise Problem(403, "Sense permís per enriquir contractes", "forbidden")
    contract = await get_scoped_contract(session, contract_id, user, authz.ScopeInfo(type="all"))
    if not contract.phase_urls:
        raise Problem(409, "El contracte no té fases publicades per enriquir", "conflict")

    # 409 connector-disabled si el connector pscp està desactivat.
    await hub.get_connector(session, "pscp")

    return await enqueue_job(
        session,
        job_type="enrich.contract",
        payload={"contract_id": contract_id, "force": True},
        created_by=user.id,
        dedup_key=f"enrich.contract:{contract_id}",
    )


async def enqueue_export(
    session: AsyncSession, data: ExportRequest, user: User, ctx: RequestContext
) -> Job:
    if authz.evaluate(user, "contracts:export") is None:
        await _audit_denied(session, user, 0, "contracts:export", ctx)
        raise Problem(403, "Sense permís per exportar contractes", "forbidden")

    # L'abast efectiu es fixa ARA i viatja al payload: el job no re-avalua.
    scope = await authz.resolve_view_scope(session, user, data.view, ctx)
    job = await enqueue_job(
        session,
        job_type="export.contracts",
        payload={
            "format": data.format,
            "user_id": user.id,
            "scope": {"type": scope.type, "department_ids": scope.department_ids},
            "filters": data.filters.model_dump(mode="json", exclude_none=True),
        },
        created_by=user.id,
    )
    await record_audit(
        session,
        actor_type=AuditActorType.USER,
        action="contracts.export",
        success=True,
        actor_id=user.id,
        resource_type="job",
        resource_id=str(job.id),
        ip=ctx.ip,
        user_agent=ctx.user_agent,
        trace_id=ctx.trace_id,
        details={"format": data.format, "view": data.view},
    )
    await session.commit()
    return job


async def bulk_assign_departments(
    session: AsyncSession,
    data: BulkAssignRequest,
    user: User,
    ctx: RequestContext,
) -> dict[str, Any]:
    if authz.evaluate(user, "contracts:bulk_assign") is None:
        await _audit_denied(session, user, 0, "contracts:bulk_assign", ctx)
        raise Problem(403, "Sense permís per a l'assignació massiva", "forbidden")

    departments = await get_departments(session, data.department_ids)
    if len(departments) != len(set(data.department_ids)):
        raise Problem(422, "Algun departament no existeix", "validation")

    contracts = await repository.get_many(session, data.contract_ids)
    missing = sorted(set(data.contract_ids) - {c.id for c in contracts})

    updated = 0
    for contract in contracts:
        before = sorted(d.code for d in contract.departments)
        if data.mode == "replace":
            new_departments = list(departments)
        else:
            current = {d.id for d in contract.departments}
            new_departments = list(contract.departments) + [
                d for d in departments if d.id not in current
            ]
        after = sorted(d.code for d in new_departments)
        if before == after:
            continue
        session.add(_history(contract, "departments", ", ".join(before), ", ".join(after), user.id))
        contract.departments = new_departments
        updated += 1

    if updated:
        await session.flush()
    await record_audit(
        session,
        actor_type=AuditActorType.USER,
        action="contracts.bulk_assign",
        success=True,
        actor_id=user.id,
        resource_type="contract",
        resource_id="bulk",
        ip=ctx.ip,
        user_agent=ctx.user_agent,
        trace_id=ctx.trace_id,
        details={
            "mode": data.mode,
            "department_ids": data.department_ids,
            "requested": len(data.contract_ids),
            "updated": updated,
            "missing": missing,
        },
    )
    await session.commit()
    return {"updated": updated, "unchanged": len(contracts) - updated, "missing": missing}


async def _audit_denied(
    session: AsyncSession, user: User, contract_id: int, action: str, ctx: RequestContext
) -> None:
    await record_audit(
        session,
        actor_type=AuditActorType.USER,
        action="authz.denied",
        success=False,
        actor_id=user.id,
        resource_type="contract",
        resource_id=str(contract_id),
        ip=ctx.ip,
        user_agent=ctx.user_agent,
        trace_id=ctx.trace_id,
        details={"action": action},
    )
    await session.commit()
