"""Tests d'integració del flux d'autenticació (BD i Redis reals).

Cada test crea el seu usuari amb correu únic i l'esborra al final.
Les entrades d'audit_log que generen són permanents per disseny
(append-only); a CI la base és efímera.
"""

from collections.abc import AsyncIterator, Iterator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.security import hash_password
from app.main import app

PASSWORD = "Contrasenya-de-prova-123"


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
async def clean_rate_limits() -> AsyncIterator[None]:
    # La IP del TestClient és sempre "testclient": sense neteja, els límits
    # per IP es filtrarien d'un test a l'altre.
    redis = Redis.from_url(settings.redis_url)
    keys = [key async for key in redis.scan_iter("rl:*")]
    if keys:
        await redis.delete(*keys)
    await redis.aclose()
    yield


@pytest.fixture
async def user_email() -> AsyncIterator[str]:
    email = f"test-{uuid4().hex[:10]}@cunit.cat"
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO users (name, email, role, password_hash) "
                "VALUES ('Usuària de Prova', :email, 'employee', :hash)"
            ),
            {"email": email, "hash": hash_password(PASSWORD)},
        )
    yield email
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM users WHERE email = :email"), {"email": email})
    await engine.dispose()


async def _last_audit(action: str, email: str | None = None) -> dict[str, object] | None:
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT action, success, details, prev_hash, entry_hash FROM audit_log "
                "WHERE action = :action "
                "AND (CAST(:email AS TEXT) IS NULL OR details->>'email' = :email) "
                "ORDER BY id DESC LIMIT 1"
            ),
            {"action": action, "email": email},
        )
        row = result.mappings().first()
    await engine.dispose()
    return dict(row) if row else None


def test_login_ok_returns_token_pair(client: TestClient, user_email: str) -> None:
    response = client.post("/api/v1/auth/login", json={"email": user_email, "password": PASSWORD})

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "Bearer"
    assert body["expires_in"] == settings.access_token_expire_minutes * 60
    assert body["access_token"] and body["refresh_token"]


async def test_login_ok_is_audited_with_hash_chain(client: TestClient, user_email: str) -> None:
    client.post("/api/v1/auth/login", json={"email": user_email, "password": PASSWORD})

    entry = await _last_audit("auth.login", user_email)

    assert entry is not None
    assert entry["success"] is True
    assert entry["entry_hash"]


def test_login_wrong_password_is_401_problem(client: TestClient, user_email: str) -> None:
    response = client.post(
        "/api/v1/auth/login", json={"email": user_email, "password": "Incorrecta-999"}
    )

    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["trace_id"]
    # Mai eco del cos: la contrasenya no apareix enlloc de la resposta.
    assert "Incorrecta-999" not in response.text


async def test_login_failure_is_audited(client: TestClient, user_email: str) -> None:
    client.post("/api/v1/auth/login", json={"email": user_email, "password": "Dolenta-123"})

    entry = await _last_audit("auth.login", user_email)

    assert entry is not None
    assert entry["success"] is False


def test_login_unknown_user_same_response(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": f"no-existeix-{uuid4().hex[:8]}@cunit.cat", "password": "Res-123456"},
    )

    assert response.status_code == 401


async def test_login_disabled_account_is_403(client: TestClient, user_email: str) -> None:
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.execute(
            text("UPDATE users SET active = false WHERE email = :email"), {"email": user_email}
        )
    await engine.dispose()

    response = client.post("/api/v1/auth/login", json={"email": user_email, "password": PASSWORD})

    assert response.status_code == 403


def test_me_requires_and_returns_user(client: TestClient, user_email: str) -> None:
    unauthenticated = client.get("/api/v1/me")
    assert unauthenticated.status_code == 401

    login = client.post("/api/v1/auth/login", json={"email": user_email, "password": PASSWORD})
    token = login.json()["access_token"]

    response = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == user_email
    assert body["role"] == "employee"
    assert body["auth_source"] == "local"
    assert "password" not in response.text and "hash" not in response.text


def test_refresh_rotates_and_detects_reuse(client: TestClient, user_email: str) -> None:
    login = client.post("/api/v1/auth/login", json={"email": user_email, "password": PASSWORD})
    first_refresh = login.json()["refresh_token"]

    rotated = client.post("/api/v1/auth/refresh", json={"refresh_token": first_refresh})
    assert rotated.status_code == 200
    second_refresh = rotated.json()["refresh_token"]
    assert second_refresh != first_refresh

    # Reutilitzar el token ja rotat ha de revocar la família sencera.
    reuse = client.post("/api/v1/auth/refresh", json={"refresh_token": first_refresh})
    assert reuse.status_code == 401

    family_dead = client.post("/api/v1/auth/refresh", json={"refresh_token": second_refresh})
    assert family_dead.status_code == 401


async def test_reuse_detection_is_audited(client: TestClient, user_email: str) -> None:
    login = client.post("/api/v1/auth/login", json={"email": user_email, "password": PASSWORD})
    first_refresh = login.json()["refresh_token"]
    client.post("/api/v1/auth/refresh", json={"refresh_token": first_refresh})
    client.post("/api/v1/auth/refresh", json={"refresh_token": first_refresh})

    entry = await _last_audit("auth.refresh_reuse")

    assert entry is not None
    assert entry["success"] is False


def test_logout_revokes_session(client: TestClient, user_email: str) -> None:
    login = client.post("/api/v1/auth/login", json={"email": user_email, "password": PASSWORD})
    access = login.json()["access_token"]
    refresh = login.json()["refresh_token"]

    response = client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {access}"})
    assert response.status_code == 204

    after_logout = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert after_logout.status_code == 401


def test_login_rate_limit_by_ip(client: TestClient) -> None:
    email = f"rate-{uuid4().hex[:8]}@cunit.cat"
    for _ in range(5):
        client.post("/api/v1/auth/login", json={"email": email, "password": "Dolenta-123"})

    sixth = client.post("/api/v1/auth/login", json={"email": email, "password": "Dolenta-123"})

    assert sixth.status_code == 429
    assert int(sixth.headers["Retry-After"]) > 0


async def test_audit_chain_links_consecutive_entries(client: TestClient, user_email: str) -> None:
    client.post("/api/v1/auth/login", json={"email": user_email, "password": PASSWORD})
    client.post("/api/v1/auth/login", json={"email": user_email, "password": PASSWORD})

    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text("SELECT prev_hash, entry_hash FROM audit_log ORDER BY id DESC LIMIT 2")
            )
        ).all()
    await engine.dispose()

    newest, previous = rows
    assert newest.prev_hash == previous.entry_hash
