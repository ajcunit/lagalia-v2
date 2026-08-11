import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.users.models import RefreshToken, User


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
