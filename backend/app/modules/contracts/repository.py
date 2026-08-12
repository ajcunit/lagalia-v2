"""Consultes de contractes amb l'abast departamental en UN SOL lloc.

El predicat de visibilitat (A2 §3) s'aplica idèntic a llistats, detalls
i subrecursos: pertànyer a un departament assignat o ser responsable.
"""

from typing import Any

from sqlalchemy import ColumnElement, Select, extract, false, func, or_, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.authz import ScopeInfo
from app.core.pagination import decode_cursor, encode_cursor
from app.modules.contractors.models import Contractor
from app.modules.contracts.models import (
    Contract,
    ContractHistoryEntry,
    Extension,
    Modification,
    contract_departments,
    contract_managers,
)

SORTABLE_FIELDS = {
    "published_at": Contract.published_at,
    "calculated_end_date": Contract.calculated_end_date,
    "award_amount": Contract.award_amount,
    "file_code": Contract.file_code,
}


def visibility_predicate(scope: ScopeInfo, user_id: int) -> ColumnElement[bool] | None:
    """None = sense restricció; altrament la condició de visibilitat."""
    if scope.type == "all":
        return None
    department_ids = scope.department_ids or []
    in_departments: ColumnElement[bool] = (
        Contract.id.in_(
            select(contract_departments.c.contract_id).where(
                contract_departments.c.department_id.in_(department_ids)
            )
        )
        if department_ids
        else false()
    )
    is_manager = Contract.id.in_(
        select(contract_managers.c.contract_id).where(contract_managers.c.user_id == user_id)
    )
    return or_(in_departments, is_manager)


async def get_visible_contract(
    session: AsyncSession, contract_id: int, scope: ScopeInfo, user_id: int
) -> Contract | None:
    """Detall dins d'abast; fora d'abast és com si no existís (404)."""
    stmt = (
        select(Contract)
        .options(selectinload(Contract.contractor), selectinload(Contract.departments))
        .where(Contract.id == contract_id)
    )
    predicate = visibility_predicate(scope, user_id)
    if predicate is not None:
        stmt = stmt.where(predicate)
    return (await session.execute(stmt)).scalar_one_or_none()


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _apply_filters(stmt: Select[Any], filters: dict[str, Any]) -> Select[Any]:
    if q := filters.get("q"):
        pattern = f"%{_escape_like(q)}%"
        stmt = stmt.where(
            or_(
                Contract.file_code.ilike(pattern),
                Contract.subject.ilike(pattern),
                Contract.raw_contractor_name.ilike(pattern),
                Contract.contractor_id.in_(
                    select(Contractor.id).where(Contractor.canonical_name.ilike(pattern))
                ),
            )
        )
    if department_id := filters.get("department_id"):
        stmt = stmt.where(
            Contract.id.in_(
                select(contract_departments.c.contract_id).where(
                    contract_departments.c.department_id == department_id
                )
            )
        )
    if filters.get("unassigned"):
        stmt = stmt.where(~Contract.id.in_(select(contract_departments.c.contract_id)))
    if contract_type := filters.get("contract_type"):
        stmt = stmt.where(Contract.contract_type == contract_type)
    if status := filters.get("status"):
        stmt = stmt.where(Contract.status == status)
    if internal_status := filters.get("internal_status"):
        stmt = stmt.where(Contract.internal_status == internal_status)
    if (expiry := filters.get("expiry_warning")) is not None:
        stmt = stmt.where(Contract.expiry_warning == expiry)
    if (finished := filters.get("possibly_finished")) is not None:
        stmt = stmt.where(Contract.possibly_finished == finished)
    if year := filters.get("year"):
        stmt = stmt.where(extract("year", Contract.published_at) == year)
    if contractor_id := filters.get("contractor_id"):
        stmt = stmt.where(Contract.contractor_id == contractor_id)
    return stmt


async def list_contracts(
    session: AsyncSession,
    *,
    scope: ScopeInfo,
    user_id: int,
    filters: dict[str, Any],
    sort_field: str = "published_at",
    descending: bool = True,
    page_size: int = 50,
    cursor: str | None = None,
) -> tuple[list[Contract], int, str | None]:
    column = SORTABLE_FIELDS[sort_field]
    predicate = visibility_predicate(scope, user_id)

    base = select(Contract)
    if predicate is not None:
        base = base.where(predicate)
    base = _apply_filters(base, filters)

    count_stmt = select(func.count()).select_from(base.subquery())
    total = (await session.execute(count_stmt)).scalar_one()

    stmt = base.options(selectinload(Contract.contractor), selectinload(Contract.departments))
    if descending:
        stmt = stmt.order_by(column.desc().nulls_last(), Contract.id.desc())
    else:
        stmt = stmt.order_by(column.asc().nulls_first(), Contract.id.asc())

    if cursor is not None:
        last_value, last_id = decode_cursor(cursor)
        keyset: Any = tuple_(column, Contract.id)
        boundary = (last_value, int(last_id))
        # Nota: el keyset amb NULLs al camp d'ordre es degrada a > id quan
        # el valor és null; suficient per als camps actuals (poc nuls).
        if last_value is None:
            stmt = stmt.where(Contract.id < last_id if descending else Contract.id > last_id)
        else:
            stmt = stmt.where(keyset < boundary if descending else keyset > boundary)

    rows = list((await session.execute(stmt.limit(page_size + 1))).scalars())
    next_cursor = None
    if len(rows) > page_size:
        rows = rows[:page_size]
        last = rows[-1]
        next_cursor = encode_cursor([getattr(last, sort_field), last.id])
    return rows, total, next_cursor


async def siblings(session: AsyncSession, contract: Contract) -> list[Contract]:
    stmt = (
        select(Contract)
        .options(selectinload(Contract.contractor), selectinload(Contract.departments))
        .where(Contract.file_code == contract.file_code, Contract.id != contract.id)
        .order_by(Contract.id.asc())
    )
    return list((await session.execute(stmt)).scalars())


async def counters(session: AsyncSession, contract_id: int) -> dict[str, int]:
    async def _count(model: Any) -> int:
        return (
            await session.execute(select(func.count()).where(model.contract_id == contract_id))
        ).scalar_one()

    return {
        "extensions": await _count(Extension),
        "modifications": await _count(Modification),
        "history": await _count(ContractHistoryEntry),
    }


async def history_page(
    session: AsyncSession, contract_id: int, *, page_size: int, cursor: str | None
) -> tuple[list[ContractHistoryEntry], int, str | None]:
    total = (
        await session.execute(
            select(func.count()).where(ContractHistoryEntry.contract_id == contract_id)
        )
    ).scalar_one()
    stmt = (
        select(ContractHistoryEntry)
        .where(ContractHistoryEntry.contract_id == contract_id)
        .order_by(ContractHistoryEntry.id.desc())
    )
    if cursor is not None:
        _, last_id = decode_cursor(cursor)
        stmt = stmt.where(ContractHistoryEntry.id < int(last_id))
    rows = list((await session.execute(stmt.limit(page_size + 1))).scalars())
    next_cursor = None
    if len(rows) > page_size:
        rows = rows[:page_size]
        next_cursor = encode_cursor([None, rows[-1].id])
    return rows, total, next_cursor


async def extensions_of(session: AsyncSession, contract_id: int) -> list[Extension]:
    stmt = (
        select(Extension)
        .where(Extension.contract_id == contract_id)
        .order_by(Extension.number.asc())
    )
    return list((await session.execute(stmt)).scalars())


async def modifications_of(session: AsyncSession, contract_id: int) -> list[Modification]:
    stmt = (
        select(Modification)
        .where(Modification.contract_id == contract_id)
        .order_by(Modification.number.asc())
    )
    return list((await session.execute(stmt)).scalars())
