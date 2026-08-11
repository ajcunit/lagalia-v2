"""Capa de persistència: engine async únic i sessions.

L'esquema evoluciona NOMÉS amb Alembic; aquí no hi ha cap create_all.
"""

from collections.abc import AsyncIterator

from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.core.config import settings

# Noms de constraint deterministes: imprescindible perquè les migracions
# d'Alembic siguin estables i reversibles.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


# Fora de producció, sense pool: el TestClient crea un event loop per petició
# i les connexions asyncpg reutilitzades entre loops queden inservibles.
_pool_kwargs: dict[str, object] = (
    {} if settings.environment == "production" else {"poolclass": NullPool}
)

engine = create_async_engine(settings.database_url, **_pool_kwargs)
session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session
