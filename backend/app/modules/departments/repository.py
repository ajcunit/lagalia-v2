from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import decode_cursor, encode_cursor, keyset_condition
from app.modules.departments.models import Department


async def get_by_id(session: AsyncSession, department_id: int) -> Department | None:
    return await session.get(Department, department_id)


async def get_by_code(session: AsyncSession, code: str) -> Department | None:
    result = await session.execute(select(Department).where(Department.code == code))
    return result.scalar_one_or_none()


async def get_many(session: AsyncSession, ids: list[int]) -> list[Department]:
    if not ids:
        return []
    result = await session.execute(select(Department).where(Department.id.in_(ids)))
    return list(result.scalars())


def _apply_filters(stmt: Select[Any], *, active: bool | None) -> Select[Any]:
    if active is not None:
        stmt = stmt.where(Department.active == active)
    return stmt


async def list_departments(
    session: AsyncSession,
    *,
    active: bool | None = None,
    page_size: int = 50,
    cursor: str | None = None,
) -> tuple[list[Department], int, str | None]:
    total = (
        await session.execute(
            _apply_filters(select(func.count()).select_from(Department), active=active)
        )
    ).scalar_one()

    stmt = _apply_filters(select(Department), active=active).order_by(
        Department.name.asc(), Department.id.asc()
    )
    if cursor is not None:
        last_name, last_id = decode_cursor(cursor)
        stmt = stmt.where(
            keyset_condition(Department.name, Department.id, last_name, last_id, descending=False)
        )

    rows = list((await session.execute(stmt.limit(page_size + 1))).scalars())
    next_cursor = None
    if len(rows) > page_size:
        rows = rows[:page_size]
        next_cursor = encode_cursor([rows[-1].name, rows[-1].id])
    return rows, total, next_cursor
