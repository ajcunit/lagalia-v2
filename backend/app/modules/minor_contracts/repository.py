"""Consultes de menors amb l'abast departamental en un sol lloc (com majors)."""

from typing import Any

from sqlalchemy import ColumnElement, Select, false, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.authz import ScopeInfo
from app.core.pagination import decode_cursor, encode_cursor, keyset_condition
from app.modules.contractors.models import Contractor
from app.modules.minor_contracts.models import MinorContract, minor_contract_departments

SORTABLE_FIELDS = {
    "award_date": MinorContract.award_date,
    "award_amount": MinorContract.award_amount,
    "file_code": MinorContract.file_code,
}


def visibility_predicate(scope: ScopeInfo) -> ColumnElement[bool] | None:
    """Els menors no tenen responsables: només pertinença departamental."""
    if scope.type == "all":
        return None
    department_ids = scope.department_ids or []
    if not department_ids:
        return false()
    return MinorContract.id.in_(
        select(minor_contract_departments.c.minor_contract_id).where(
            minor_contract_departments.c.department_id.in_(department_ids)
        )
    )


async def get_visible_minor(
    session: AsyncSession, minor_id: int, scope: ScopeInfo
) -> MinorContract | None:
    stmt = (
        select(MinorContract)
        .options(
            selectinload(MinorContract.departments),
            selectinload(MinorContract.contractor),
        )
        .where(MinorContract.id == minor_id)
    )
    predicate = visibility_predicate(scope)
    if predicate is not None:
        stmt = stmt.where(predicate)
    return (await session.execute(stmt)).scalar_one_or_none()


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _apply_filters(stmt: Select[Any], filters: dict[str, Any]) -> Select[Any]:
    if q := filters.get("q"):
        pattern = f"%{_escape_like(q)}%"
        stmt = stmt.where(
            MinorContract.file_code.ilike(pattern)
            | MinorContract.description.ilike(pattern)
            | MinorContract.contractor_id.in_(
                select(Contractor.id).where(Contractor.canonical_name.ilike(pattern))
            )
        )
    if fiscal_year := filters.get("fiscal_year"):
        stmt = stmt.where(MinorContract.fiscal_year == fiscal_year)
    if contract_type := filters.get("contract_type"):
        stmt = stmt.where(MinorContract.contract_type == contract_type)
    if department_id := filters.get("department_id"):
        stmt = stmt.where(
            MinorContract.id.in_(
                select(minor_contract_departments.c.minor_contract_id).where(
                    minor_contract_departments.c.department_id == department_id
                )
            )
        )
    if filters.get("unassigned"):
        stmt = stmt.where(
            ~MinorContract.id.in_(select(minor_contract_departments.c.minor_contract_id))
        )
    if (settled := filters.get("settled")) is not None:
        condition = MinorContract.settlement_date.is_not(None)
        stmt = stmt.where(condition if settled else ~condition)
    return stmt


async def list_minors(
    session: AsyncSession,
    *,
    scope: ScopeInfo,
    filters: dict[str, Any],
    sort_field: str = "award_date",
    descending: bool = True,
    page_size: int = 50,
    cursor: str | None = None,
) -> tuple[list[MinorContract], int, str | None]:
    column = SORTABLE_FIELDS[sort_field]
    base = select(MinorContract)
    predicate = visibility_predicate(scope)
    if predicate is not None:
        base = base.where(predicate)
    base = _apply_filters(base, filters)

    total = (await session.execute(select(func.count()).select_from(base.subquery()))).scalar_one()

    stmt = base.options(
        selectinload(MinorContract.departments), selectinload(MinorContract.contractor)
    )
    if descending:
        stmt = stmt.order_by(column.desc().nulls_last(), MinorContract.id.desc())
    else:
        stmt = stmt.order_by(column.asc().nulls_first(), MinorContract.id.asc())

    if cursor is not None:
        last_value, last_id = decode_cursor(cursor)
        stmt = stmt.where(
            keyset_condition(column, MinorContract.id, last_value, last_id, descending=descending)
        )

    rows = list((await session.execute(stmt.limit(page_size + 1))).scalars())
    next_cursor = None
    if len(rows) > page_size:
        rows = rows[:page_size]
        next_cursor = encode_cursor([getattr(rows[-1], sort_field), rows[-1].id])
    return rows, total, next_cursor
