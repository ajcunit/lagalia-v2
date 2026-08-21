"""Rànquing unificat d'adjudicataris (majors + menors) i cua de duplicats."""

from decimal import Decimal
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import decode_cursor, encode_cursor
from app.modules.contractors.models import (
    Contractor,
    ContractorAlias,
    ContractorDuplicate,
    ContractorDuplicateStatus,
)
from app.modules.contracts.models import Contract
from app.modules.minor_contracts.models import MinorContract

_ZERO = Decimal("0")

_contracts_agg = (
    select(
        Contract.contractor_id.label("contractor_id"),
        func.count().label("contracts_count"),
        func.coalesce(func.sum(Contract.award_amount), 0).label("contracts_amount"),
    )
    .where(Contract.contractor_id.is_not(None))
    .group_by(Contract.contractor_id)
    .subquery()
)

_minors_agg = (
    select(
        MinorContract.contractor_id.label("contractor_id"),
        func.count().label("minor_count"),
        func.coalesce(func.sum(MinorContract.award_amount), 0).label("minor_amount"),
    )
    .where(MinorContract.contractor_id.is_not(None))
    .group_by(MinorContract.contractor_id)
    .subquery()
)

_total_amount = (
    func.coalesce(_contracts_agg.c.contracts_amount, 0)
    + func.coalesce(_minors_agg.c.minor_amount, 0)
).label("total_amount")

RANKING_SORT_KEYS = ("total_amount", "contracts_count", "name")


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _ranking_base() -> Select[Any]:
    return (
        select(
            Contractor,
            func.coalesce(_contracts_agg.c.contracts_count, 0).label("contracts_count"),
            func.coalesce(_contracts_agg.c.contracts_amount, 0).label("contracts_amount"),
            func.coalesce(_minors_agg.c.minor_count, 0).label("minor_count"),
            func.coalesce(_minors_agg.c.minor_amount, 0).label("minor_amount"),
            _total_amount,
        )
        .outerjoin(_contracts_agg, _contracts_agg.c.contractor_id == Contractor.id)
        .outerjoin(_minors_agg, _minors_agg.c.contractor_id == Contractor.id)
    )


def row_to_ranking(row: Any) -> dict[str, Any]:
    contractor: Contractor = row.Contractor
    return {
        "id": contractor.id,
        "name": contractor.canonical_name,
        "tax_id": contractor.tax_id,
        "contracts_count": int(row.contracts_count),
        "contracts_amount": Decimal(row.contracts_amount or _ZERO),
        "minor_count": int(row.minor_count),
        "minor_amount": Decimal(row.minor_amount or _ZERO),
        "total_amount": Decimal(row.total_amount or _ZERO),
    }


async def ranking(
    session: AsyncSession,
    *,
    q: str | None,
    sort_key: str = "total_amount",
    descending: bool = True,
    page_size: int = 50,
    cursor: str | None = None,
) -> tuple[list[dict[str, Any]], int, str | None]:
    stmt = _ranking_base()
    if q:
        pattern = f"%{_escape_like(q)}%"
        stmt = stmt.where(
            Contractor.canonical_name.ilike(pattern)
            | Contractor.tax_id.ilike(pattern)
            | Contractor.id.in_(
                select(ContractorAlias.contractor_id).where(ContractorAlias.alias.ilike(pattern))
            )
        )

    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()

    order_column = {
        "total_amount": _total_amount,
        "contracts_count": func.coalesce(_contracts_agg.c.contracts_count, 0),
        "name": Contractor.canonical_name,
    }[sort_key]
    if descending:
        stmt = stmt.order_by(order_column.desc(), Contractor.id.desc())
    else:
        stmt = stmt.order_by(order_column.asc(), Contractor.id.asc())

    # Paginació per offset dins del cursor: el rànquing s'ordena per agregats
    # (mutables entre pàgines); el keyset per valor no és estable aquí.
    offset = 0
    if cursor is not None:
        offset_value, _ = decode_cursor(cursor)
        offset = int(offset_value or 0)

    rows = (await session.execute(stmt.offset(offset).limit(page_size + 1))).all()
    next_cursor = None
    if len(rows) > page_size:
        rows = rows[:page_size]
        next_cursor = encode_cursor([offset + page_size, 0])
    return [row_to_ranking(r) for r in rows], total, next_cursor


async def profile(session: AsyncSession, contractor_id: int) -> dict[str, Any] | None:
    stmt = _ranking_base().where(Contractor.id == contractor_id)
    row = (await session.execute(stmt)).first()
    if row is None:
        return None
    aliases = list(
        (
            await session.execute(
                select(ContractorAlias.alias).where(ContractorAlias.contractor_id == contractor_id)
            )
        ).scalars()
    )
    contractor: Contractor = row.Contractor
    return {
        **row_to_ranking(row),
        "nationality": contractor.nationality,
        "company_type": contractor.company_type,
        "third_sector": contractor.third_sector,
        "phone": contractor.phone,
        "email": contractor.email,
        "aliases": sorted(aliases),
        "created_at": contractor.created_at,
    }


async def duplicates_page(
    session: AsyncSession,
    *,
    status: ContractorDuplicateStatus,
    page_size: int,
    cursor: str | None,
) -> tuple[list[ContractorDuplicate], int, str | None]:
    base = select(ContractorDuplicate).where(ContractorDuplicate.status == status)
    if status == ContractorDuplicateStatus.PENDING:
        # Un pendent sense els dos costats vius és un residu (el contractista
        # va desaparèixer per una fusió externa): no es pot resoldre.
        base = base.where(
            ContractorDuplicate.contractor_id_1.is_not(None),
            ContractorDuplicate.contractor_id_2.is_not(None),
        )
    total = (await session.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    # Els detectats més recentment, primer.
    stmt = base.order_by(ContractorDuplicate.id.desc())
    if cursor is not None:
        _, last_id = decode_cursor(cursor)
        stmt = stmt.where(ContractorDuplicate.id < int(last_id))
    rows = list((await session.execute(stmt.limit(page_size + 1))).scalars())
    next_cursor = None
    if len(rows) > page_size:
        rows = rows[:page_size]
        next_cursor = encode_cursor([None, rows[-1].id])
    return rows, total, next_cursor


async def duplicate_groups(
    session: AsyncSession, *, page_size: int, cursor: str | None, q: str | None = None
) -> tuple[list[dict[str, Any]], int, str | None]:
    """Grups de NIF amb parells pendents, ordenats per mida (B-011)."""
    pending_1 = select(ContractorDuplicate.contractor_id_1).where(
        ContractorDuplicate.status == ContractorDuplicateStatus.PENDING
    )
    pending_2 = select(ContractorDuplicate.contractor_id_2).where(
        ContractorDuplicate.status == ContractorDuplicateStatus.PENDING
    )
    tax_ids_stmt = (
        select(Contractor.tax_id, func.count().label("members"))
        .where(
            Contractor.tax_id.is_not(None),
            Contractor.id.in_(pending_1.union(pending_2)),
        )
        .group_by(Contractor.tax_id)
        .order_by(func.count().desc(), Contractor.tax_id.asc())
    )
    if q:
        pattern = f"%{_escape_like(q)}%"
        tax_ids_stmt = tax_ids_stmt.where(
            Contractor.tax_id.ilike(pattern) | Contractor.canonical_name.ilike(pattern)
        )
    total = (
        await session.execute(select(func.count()).select_from(tax_ids_stmt.subquery()))
    ).scalar_one()

    offset = 0
    if cursor is not None:
        offset_value, _ = decode_cursor(cursor)
        offset = int(offset_value or 0)
    tax_rows = (await session.execute(tax_ids_stmt.offset(offset).limit(page_size + 1))).all()
    next_cursor = None
    if len(tax_rows) > page_size:
        tax_rows = tax_rows[:page_size]
        next_cursor = encode_cursor([offset + page_size, 0])

    groups: list[dict[str, Any]] = []
    for tax_id, _members in tax_rows:
        member_stmt = (
            _ranking_base()
            .where(Contractor.tax_id == tax_id)
            .order_by(_total_amount.desc(), Contractor.id.asc())
        )
        members = [row_to_ranking(r) for r in (await session.execute(member_stmt)).all()]
        groups.append({"tax_id": tax_id, "contractors": members})
    return groups, total, next_cursor


async def ranking_by_id(session: AsyncSession, contractor_id: int) -> dict[str, Any] | None:
    row = (await session.execute(_ranking_base().where(Contractor.id == contractor_id))).first()
    return row_to_ranking(row) if row else None


async def minor_totals(session: AsyncSession, contractor_id: int) -> list[dict[str, Any]]:
    """Suma dels menors per exercici i tipus (specs/contractor-economic-status.md).

    Agregat GLOBAL a propòsit: el control del límit de menors per
    adjudicatari és sobre tot l'ens, no sobre el departament de qui mira.
    """
    rows = (
        await session.execute(
            select(
                MinorContract.fiscal_year,
                MinorContract.contract_type,
                func.count().label("total"),
                func.coalesce(func.sum(MinorContract.award_amount), 0).label("amount"),
            )
            .where(MinorContract.contractor_id == contractor_id)
            .group_by(MinorContract.fiscal_year, MinorContract.contract_type)
            .order_by(MinorContract.fiscal_year.desc().nulls_last())
        )
    ).all()

    years: dict[int | None, dict[str, Any]] = {}
    for row in rows:
        year = years.setdefault(
            row.fiscal_year,
            {"fiscal_year": row.fiscal_year, "count": 0, "amount": Decimal(0), "by_type": []},
        )
        year["count"] += int(row.total)
        year["amount"] += row.amount
        year["by_type"].append(
            {"contract_type": row.contract_type, "count": int(row.total), "amount": row.amount}
        )
    return list(years.values())
