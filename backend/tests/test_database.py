"""Tests d'integració de l'esquema (migració 0001).

Requereixen un PostgreSQL amb `alembic upgrade head` aplicat (la CI ho fa
abans de pytest; en local, el docker compose d'infraestructura).
Cada test treballa dins una transacció que es reverteix: no deixen rastre.
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings

EXPECTED_TABLES = {"departments", "users", "user_departments", "refresh_tokens", "audit_log"}


@pytest.fixture
async def conn() -> AsyncIterator[AsyncConnection]:
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    async with engine.connect() as connection:
        yield connection
        await connection.rollback()
    await engine.dispose()


async def _insert_user(conn: AsyncConnection, email: str) -> int:
    result = await conn.execute(
        text(
            "INSERT INTO users (name, email, role) VALUES ('Test', :email, 'employee') RETURNING id"
        ),
        {"email": email},
    )
    return int(result.scalar_one())


async def test_expected_tables_exist(conn: AsyncConnection) -> None:
    result = await conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))
    tables = {row[0] for row in result}

    assert EXPECTED_TABLES <= tables


async def test_audit_log_rejects_update_and_delete(conn: AsyncConnection) -> None:
    await conn.execute(
        text(
            "INSERT INTO audit_log (actor_type, action, success) "
            "VALUES ('system', 'test.append_only', true)"
        )
    )

    with pytest.raises(DBAPIError, match="append-only"):
        await conn.execute(text("UPDATE audit_log SET action = 'tampered'"))
    await conn.rollback()

    await conn.execute(
        text(
            "INSERT INTO audit_log (actor_type, action, success) "
            "VALUES ('system', 'test.append_only', true)"
        )
    )
    with pytest.raises(DBAPIError, match="append-only"):
        await conn.execute(text("DELETE FROM audit_log WHERE action = 'test.append_only'"))
    await conn.rollback()


async def test_updated_at_changes_on_update(conn: AsyncConnection) -> None:
    await conn.execute(
        text("INSERT INTO departments (code, name) VALUES ('TST-UPD', 'Departament de prova')")
    )
    before = (
        await conn.execute(text("SELECT updated_at FROM departments WHERE code = 'TST-UPD'"))
    ).scalar_one()

    await conn.execute(text("UPDATE departments SET name = 'Canviat' WHERE code = 'TST-UPD'"))
    after = (
        await conn.execute(text("SELECT updated_at FROM departments WHERE code = 'TST-UPD'"))
    ).scalar_one()

    assert after > before


async def test_email_unique_is_case_insensitive(conn: AsyncConnection) -> None:
    await _insert_user(conn, "Cas.Sensible@cunit.cat")

    with pytest.raises(IntegrityError):
        await _insert_user(conn, "cas.sensible@CUNIT.CAT")
    await conn.rollback()


async def test_refresh_token_cascade_on_user_delete(conn: AsyncConnection) -> None:
    user_id = await _insert_user(conn, f"cascade-{uuid4().hex[:8]}@cunit.cat")
    await conn.execute(
        text(
            "INSERT INTO refresh_tokens (token_hash, user_id, family_id, expires_at) "
            "VALUES (:h, :uid, :fam, :exp)"
        ),
        {
            "h": uuid4().hex,
            "uid": user_id,
            "fam": str(uuid4()),
            "exp": datetime.now(UTC) + timedelta(days=7),
        },
    )

    await conn.execute(text("DELETE FROM users WHERE id = :uid"), {"uid": user_id})
    remaining = (
        await conn.execute(
            text("SELECT count(*) FROM refresh_tokens WHERE user_id = :uid"), {"uid": user_id}
        )
    ).scalar_one()

    assert remaining == 0
