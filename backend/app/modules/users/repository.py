import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Select, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.pagination import decode_cursor, encode_cursor, keyset_condition
from app.modules.users.models import RefreshToken, User, UserRole, user_departments

# Camps d'ordre admesos a GET /users (contracte: name, -created_at...).
SORTABLE_FIELDS = {"name": User.name, "created_at": User.created_at}


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    result = await session.execute(
        select(User).options(selectinload(User.departments)).where(User.email == email)
    )
    return result.scalar_one_or_none()


async def get_user_by_id(session: AsyncSession, user_id: int) -> User | None:
    result = await session.execute(
        select(User).options(selectinload(User.departments)).where(User.id == user_id)
    )
    return result.scalar_one_or_none()


async def create_refresh_token(
    session: AsyncSession,
    *,
    token_hash: str,
    user_id: int,
    family_id: uuid.UUID,
    expires_at: datetime,
    created_ip: str | None,
) -> RefreshToken:
    token = RefreshToken(
        token_hash=token_hash,
        user_id=user_id,
        family_id=family_id,
        expires_at=expires_at,
        created_ip=created_ip,
    )
    session.add(token)
    await session.flush()
    return token


async def get_refresh_token_by_hash(session: AsyncSession, token_hash: str) -> RefreshToken | None:
    result = await session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    return result.scalar_one_or_none()


async def revoke_refresh_token(session: AsyncSession, token: RefreshToken) -> None:
    token.revoked_at = datetime.now(UTC)
    await session.flush()


async def revoke_token_family(session: AsyncSession, family_id: uuid.UUID) -> None:
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=func.now())
    )


async def revoke_all_user_tokens(session: AsyncSession, user_id: int) -> None:
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=func.now())
    )


def _apply_filters(
    stmt: Select[Any],
    *,
    active: bool | None,
    role: UserRole | None,
    department_id: int | None,
) -> Select[Any]:
    if active is not None:
        stmt = stmt.where(User.active == active)
    if role is not None:
        stmt = stmt.where(User.role == role)
    if department_id is not None:
        stmt = stmt.where(
            User.id.in_(
                select(user_departments.c.user_id).where(
                    user_departments.c.department_id == department_id
                )
            )
        )
    return stmt


async def list_users(
    session: AsyncSession,
    *,
    active: bool | None = None,
    role: UserRole | None = None,
    department_id: int | None = None,
    sort_field: str = "name",
    descending: bool = False,
    page_size: int = 50,
    cursor: str | None = None,
) -> tuple[list[User], int, str | None]:
    """Keyset pagination sobre (camp d'ordre, id). Retorna (usuaris, total, next_cursor)."""
    column = SORTABLE_FIELDS[sort_field]

    total_stmt = _apply_filters(
        select(func.count()).select_from(User),
        active=active,
        role=role,
        department_id=department_id,
    )
    total = (await session.execute(total_stmt)).scalar_one()

    stmt = _apply_filters(
        select(User).options(selectinload(User.departments)),
        active=active,
        role=role,
        department_id=department_id,
    )
    if descending:
        stmt = stmt.order_by(column.desc(), User.id.desc())
    else:
        stmt = stmt.order_by(column.asc(), User.id.asc())

    if cursor is not None:
        last_value, last_id = decode_cursor(cursor)
        stmt = stmt.where(
            keyset_condition(column, User.id, last_value, last_id, descending=descending)
        )

    rows = list((await session.execute(stmt.limit(page_size + 1))).scalars())
    next_cursor = None
    if len(rows) > page_size:
        rows = rows[:page_size]
        last = rows[-1]
        next_cursor = encode_cursor([getattr(last, sort_field), last.id])
    return rows, total, next_cursor


async def list_department_users(session: AsyncSession, department_id: int) -> list[User]:
    stmt = (
        select(User)
        .options(selectinload(User.departments))
        .join(user_departments, user_departments.c.user_id == User.id)
        .where(user_departments.c.department_id == department_id)
        .order_by(User.name.asc())
    )
    return list((await session.execute(stmt)).scalars())
