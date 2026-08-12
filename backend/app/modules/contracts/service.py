"""Casos d'ús de contractes: llistat/detall dins d'abast, edició per matriu.

Fora d'abast → 404 (mai es revela l'existència). L'edició distingeix
contracts:update (tots els camps) de contracts:update_warning (només
warning_months_override, dins d'abast).
"""

from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import authz
from app.core.problems import Problem
from app.modules.audit.models import AuditActorType
from app.modules.audit.service import record_audit
from app.modules.contracts import repository
from app.modules.contracts.models import (
    ChangeType,
    Contract,
    ContractHistoryEntry,
    ContractSource,
)
from app.modules.contracts.schemas import ContractCreate, ContractUpdate
from app.modules.departments.repository import get_many as get_departments
from app.modules.users.models import User
from app.modules.users.service import RequestContext

_WARNING_ONLY_FIELDS = {"warning_months_override"}


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
