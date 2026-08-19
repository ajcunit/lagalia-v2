"""Integració del setup inicial.

El camí d'èxit necessita un sistema amb 0 usuaris: es prova contra una
base de dades temporal creada al vol amb les migracions aplicades.
"""

import os
import subprocess
import sys
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.problems import Problem
from app.core.security import verify_password
from app.modules.setup import service
from app.modules.setup.schemas import InitializeRequest
from app.modules.users.service import RequestContext
from tests.conftest import MakeUser, TestUser

CTX = RequestContext(ip=None, user_agent="pytest", trace_id="setup-test")


def _payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "name": "Administradora Inicial",
        "email": f"setup-{uuid4().hex[:8]}@cunit.cat",
        "password": "Contrasenya-Inicial-42",
        "organization_name": "Ajuntament de Cunit",
        "ine10_code": "4305160009",
    }
    payload.update(overrides)
    return payload


async def test_status_reflects_user_count(api_client: TestClient) -> None:
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    async with engine.connect() as conn:
        count = (await conn.execute(text("SELECT count(*) FROM users"))).scalar_one()
    await engine.dispose()

    response = api_client.get("/api/v1/setup/status")

    assert response.status_code == 200
    assert response.json() == {"needs_setup": count == 0}


async def test_initialize_when_users_exist_is_403(
    api_client: TestClient, make_user: MakeUser
) -> None:
    _user: TestUser = await make_user("employee")  # garanteix count > 0

    response = api_client.post("/api/v1/setup/initialize", json=_payload())

    assert response.status_code == 403
    assert response.json()["type"].endswith("already-initialized")


async def test_initialize_rate_limit(api_client: TestClient, make_user: MakeUser) -> None:
    await make_user("employee")

    for _ in range(3):
        blocked = api_client.post("/api/v1/setup/initialize", json=_payload())
        assert blocked.status_code == 403

    fourth = api_client.post("/api/v1/setup/initialize", json=_payload())

    assert fourth.status_code == 429
    assert int(fourth.headers["Retry-After"]) > 0


def test_initialize_weak_password_is_422(api_client: TestClient) -> None:
    response = api_client.post("/api/v1/setup/initialize", json=_payload(password="curta1A"))

    assert response.status_code == 422
    assert "curta1A" not in response.text


def test_initialize_bad_ine10_is_422(api_client: TestClient) -> None:
    response = api_client.post("/api/v1/setup/initialize", json=_payload(ine10_code="123"))

    assert response.status_code == 422


@pytest.fixture
async def empty_database_url() -> AsyncIterator[str]:
    """Crea una BD temporal amb les migracions aplicades i l'esborra al final."""
    db_name = f"lagalia_setup_test_{uuid4().hex[:8]}"
    base_url = settings.database_url.rsplit("/", 1)[0]
    admin_engine = create_async_engine(
        f"{base_url}/postgres", poolclass=NullPool, isolation_level="AUTOCOMMIT"
    )
    async with admin_engine.connect() as conn:
        await conn.execute(text(f'CREATE DATABASE "{db_name}"'))  # lint-ok: DDL, nom generat

    temp_url = f"{base_url}/{db_name}"
    env = os.environ | {"DATABASE_URL": temp_url}
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr

    yield temp_url

    async with admin_engine.connect() as conn:
        await conn.execute(text(f'DROP DATABASE "{db_name}" WITH (FORCE)'))  # lint-ok: DDL
    await admin_engine.dispose()


async def test_initialize_on_empty_database(empty_database_url: str) -> None:
    engine = create_async_engine(empty_database_url, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    data = InitializeRequest(
        name="Administradora Inicial",
        email="admin-inicial@cunit.cat",
        password="Contrasenya-Inicial-42",
        organization_name="Ajuntament de Cunit",
        ine10_code="4305160009",
    )

    async with factory() as session:
        assert await service.needs_setup(session) is True
        admin = await service.initialize(session, data, CTX)

    assert admin.role.value == "admin"

    async with factory() as session:
        assert await service.needs_setup(session) is False

    async with engine.connect() as conn:
        row = (
            await conn.execute(
                text("SELECT role, password_hash FROM users WHERE email = :email"),
                {"email": "admin-inicial@cunit.cat"},
            )
        ).one()
        assert row.role == "admin"  # lint-ok: assercio de fila, no authz
        assert verify_password("Contrasenya-Inicial-42", row.password_hash)

        keys = {r[0] for r in await conn.execute(text("SELECT key FROM settings"))}
        assert {"setup.completed_at", "org.name", "org.ine10_code"} <= keys

        audit = (
            await conn.execute(
                text(
                    "SELECT success FROM audit_log WHERE action = 'setup.initialize' "
                    "ORDER BY id DESC LIMIT 1"
                )
            )
        ).scalar_one()
        assert audit is True

    # Segona inicialització: 403 encara que la primera acabi de passar.
    async with factory() as session:
        with pytest.raises(Problem) as excinfo:
            await service.initialize(session, data, CTX)
    assert excinfo.value.status_code == 403

    await engine.dispose()
