"""Entorn de test: secrets sintètics abans de qualsevol import de l'app.

Els tests no depenen del .env del desenvolupador: aquí es fixen els dos
secrets obligatoris amb valors vàlids només per a test. També hi ha les
fixtures compartides d'integració (client HTTP i fàbrica d'usuaris).
"""

import base64
import os

os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production-0123456789")
os.environ.setdefault("ENCRYPTION_KEY", base64.b64encode(b"\x00" * 32).decode())
os.environ.setdefault("ENVIRONMENT", "development")
# Cua pròpia dels tests: un worker viu de desenvolupament no ha d'executar
# els jobs que els tests encuen (trepitjaria l'estat que fixen a mà).
os.environ["JOBS_QUEUE_NAME"] = "arq:test-queue"

# ── BD efímera de la bateria (B-014) ─────────────────────────────────────
# Els tests NO comparteixen mai la BD de dev: es recrea lagalia_test a cada
# sessió (DROP+CREATE+Alembic) i DATABASE_URL hi apunta ABANS de cap import
# de l'app. Un test que "restaura" malament ja no pot trencar l'entorn viu.
# Redis propi de la bateria (db 1): el dedupe diari, els rate limits i la
# cua no comparteixen res amb el worker/scheduler vius (db 0).
_DEV_REDIS = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
os.environ["REDIS_URL"] = _DEV_REDIS.rsplit("/", 1)[0] + "/1"

_DEV_DB_URL = os.environ.get(
    "DATABASE_URL", "postgresql+asyncpg://lagalia:lagalia@localhost:5432/lagalia"
)
_TEST_DB_NAME = "lagalia_test"
_BASE_URL, _, _ = _DEV_DB_URL.rpartition("/")
os.environ["DATABASE_URL"] = f"{_BASE_URL}/{_TEST_DB_NAME}"


def _prepare_test_database() -> None:
    import asyncio
    from pathlib import Path

    import asyncpg

    async def recreate() -> None:
        admin = await asyncpg.connect(
            _BASE_URL.replace("postgresql+asyncpg://", "postgresql://") + "/postgres"
        )
        try:
            await admin.execute(f"DROP DATABASE IF EXISTS {_TEST_DB_NAME} WITH (FORCE)")
            await admin.execute(f"CREATE DATABASE {_TEST_DB_NAME}")
        finally:
            await admin.close()

    async def flush_test_redis() -> None:
        # La BD es recrea i els ids reprenen d'1: les claus de dedupe de la
        # bateria anterior (db 1, TTL 20 h) col·lidirien amb els ids nous.
        from redis.asyncio import Redis

        redis = Redis.from_url(os.environ["REDIS_URL"])
        await redis.flushdb()
        await redis.aclose()

    asyncio.run(recreate())
    asyncio.run(flush_test_redis())

    from alembic.config import Config

    from alembic import command

    backend_dir = Path(__file__).resolve().parents[1]
    config = Config(str(backend_dir / "alembic.ini"))
    config.set_main_option("script_location", str(backend_dir / "alembic"))
    command.upgrade(config, "head")


_prepare_test_database()

from collections.abc import AsyncIterator, Awaitable, Callable, Iterator  # noqa: E402
from dataclasses import dataclass, field  # noqa: E402
from uuid import uuid4  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

TEST_PASSWORD = "Contrasenya-de-prova-123"


@dataclass
class TestUser:
    __test__ = False  # no és una classe de tests

    id: int
    email: str
    department_ids: list[int] = field(default_factory=list)


MakeUser = Callable[..., Awaitable[TestUser]]


@pytest.fixture(autouse=True)
async def clean_rate_limit_counters() -> AsyncIterator[None]:
    """La IP del TestClient és sempre "testclient": sense neteja, els
    límits per IP es filtrarien d'un test a l'altre."""
    from redis.asyncio import Redis

    from app.core.config import settings

    redis = Redis.from_url(settings.redis_url)
    keys = [key async for key in redis.scan_iter("rl:*")]
    if keys:
        await redis.delete(*keys)
    await redis.aclose()
    yield


@pytest.fixture
def api_client() -> Iterator[TestClient]:
    from app.main import app

    with TestClient(app) as client:
        yield client


@pytest.fixture
async def make_user() -> AsyncIterator[MakeUser]:
    """Crea usuaris (i opcionalment un departament) amb neteja al final."""
    from app.core.config import settings
    from app.core.security import hash_password

    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    user_ids: list[int] = []
    department_ids: list[int] = []

    async def _make(
        role: str,
        *,
        can_plan: bool = False,
        can_audit: bool = False,
        with_department: bool = False,
        password: str | None = TEST_PASSWORD,
    ) -> TestUser:
        email = f"itest-{uuid4().hex[:10]}@cunit.cat"
        async with engine.begin() as conn:
            user_id = (
                await conn.execute(
                    text(
                        "INSERT INTO users (name, email, role, password_hash, can_plan, can_audit) "
                        "VALUES ('Usuària de Prova', :email, :role, :hash, :can_plan, :can_audit) "
                        "RETURNING id"
                    ),
                    {
                        "email": email,
                        "role": role,
                        "hash": hash_password(password) if password else None,
                        "can_plan": can_plan,
                        "can_audit": can_audit,
                    },
                )
            ).scalar_one()
            user = TestUser(id=user_id, email=email)
            if with_department:
                dept_id = (
                    await conn.execute(
                        text(
                            "INSERT INTO departments (code, name) "
                            "VALUES (:code, 'Departament de Prova') RETURNING id"
                        ),
                        {"code": f"TST-{uuid4().hex[:8]}"},
                    )
                ).scalar_one()
                await conn.execute(
                    text("INSERT INTO user_departments (user_id, department_id) VALUES (:u, :d)"),
                    {"u": user_id, "d": dept_id},
                )
                user.department_ids.append(dept_id)
                department_ids.append(dept_id)
        user_ids.append(user_id)
        return user

    yield _make

    async with engine.begin() as conn:
        for user_id in user_ids:
            await conn.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})
        for dept_id in department_ids:
            await conn.execute(text("DELETE FROM departments WHERE id = :id"), {"id": dept_id})
    await engine.dispose()


def login_headers(client: TestClient, email: str) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": TEST_PASSWORD})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}
