"""Integració del motor d'autorització: /me/permissions, denegacions
auditades i validació de la Vista Admin (BD real)."""

import uuid
from collections.abc import AsyncIterator, Callable, Iterator
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from app.core import authz
from app.core.config import settings
from app.core.db import session_factory
from app.core.problems import Problem
from app.core.security import hash_password
from app.main import app
from app.modules.users import repository
from app.modules.users.dependencies import CurrentSession
from app.modules.users.service import RequestContext

PASSWORD = "Contrasenya-de-prova-123"

MakeUser = Callable[..., Any]


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
async def make_user() -> AsyncIterator[MakeUser]:
    engine: AsyncEngine = create_async_engine(settings.database_url, poolclass=NullPool)
    created_users: list[str] = []
    created_departments: list[int] = []

    async def _make(
        role: str,
        *,
        can_plan: bool = False,
        can_audit: bool = False,
        with_department: bool = False,
    ) -> tuple[str, list[int]]:
        email = f"authz-{uuid4().hex[:10]}@cunit.cat"
        department_ids: list[int] = []
        async with engine.begin() as conn:
            user_id = (
                await conn.execute(
                    text(
                        "INSERT INTO users (name, email, role, password_hash, can_plan, can_audit) "
                        "VALUES ('Test AuthZ', :email, :role, :hash, :can_plan, :can_audit) "
                        "RETURNING id"
                    ),
                    {
                        "email": email,
                        "role": role,
                        "hash": hash_password(PASSWORD),
                        "can_plan": can_plan,
                        "can_audit": can_audit,
                    },
                )
            ).scalar_one()
            if with_department:
                dept_id = (
                    await conn.execute(
                        text(
                            "INSERT INTO departments (code, name) "
                            "VALUES (:code, 'Departament AuthZ') RETURNING id"
                        ),
                        {"code": f"AZ-{uuid4().hex[:8]}"},
                    )
                ).scalar_one()
                await conn.execute(
                    text("INSERT INTO user_departments (user_id, department_id) VALUES (:u, :d)"),
                    {"u": user_id, "d": dept_id},
                )
                department_ids.append(dept_id)
                created_departments.append(dept_id)
        created_users.append(email)
        return email, department_ids

    yield _make

    async with engine.begin() as conn:
        for email in created_users:
            await conn.execute(text("DELETE FROM users WHERE email = :email"), {"email": email})
        for dept_id in created_departments:
            await conn.execute(text("DELETE FROM departments WHERE id = :id"), {"id": dept_id})
    await engine.dispose()


def _login(client: TestClient, email: str) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def test_admin_permissions(client: TestClient, make_user: MakeUser) -> None:
    email, _ = await make_user("admin")

    body = client.get("/api/v1/me/permissions", headers=_login(client, email)).json()

    assert body["role"] == "admin"
    assert body["scope"] == {"type": "all", "department_ids": None}
    assert body["can_switch_view"] is True
    assert "users:write" in body["actions"]
    assert "config:write" in body["actions"]


async def test_employee_permissions_departmental(client: TestClient, make_user: MakeUser) -> None:
    email, department_ids = await make_user("employee", with_department=True)

    body = client.get("/api/v1/me/permissions", headers=_login(client, email)).json()

    assert body["role"] == "employee"
    assert body["scope"] == {"type": "departments", "department_ids": department_ids}
    assert body["can_switch_view"] is False
    assert "contracts:read" in body["actions"]
    assert "users:write" not in body["actions"]
    assert "plan:write" not in body["actions"]  # sense can_plan


async def test_employee_flag_unlocks_action(client: TestClient, make_user: MakeUser) -> None:
    email, _ = await make_user("employee", can_plan=True)

    body = client.get("/api/v1/me/permissions", headers=_login(client, email)).json()

    assert "plan:write" in body["actions"]


async def _current_session_for(email: str) -> CurrentSession:
    async with session_factory() as session:
        user = await repository.get_user_by_email(session, email)
    assert user is not None
    return CurrentSession(user=user, session_id=uuid.uuid4())


async def _last_denial(actor_id: int) -> dict[str, Any] | None:
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    async with engine.connect() as conn:
        row = (
            (
                await conn.execute(
                    text(
                        "SELECT action, resource_id, success FROM audit_log "
                        "WHERE action = 'authz.denied' AND actor_id = :actor "
                        "ORDER BY id DESC LIMIT 1"
                    ),
                    {"actor": actor_id},
                )
            )
            .mappings()
            .first()
        )
    await engine.dispose()
    return dict(row) if row else None


async def test_denied_action_raises_403_and_is_audited(make_user: MakeUser) -> None:
    email, _ = await make_user("employee")
    current = await _current_session_for(email)
    ctx = RequestContext(ip=None, user_agent="pytest", trace_id=uuid4().hex)

    authorize = authz.Authorize("config:write")
    async with session_factory() as session:
        with pytest.raises(Problem) as excinfo:
            await authorize(current=current, session=session, ctx=ctx)

    assert excinfo.value.status_code == 403

    denial = await _last_denial(current.user.id)
    assert denial is not None
    assert denial["resource_id"] == "config:write"
    assert denial["success"] is False


async def test_authorized_action_returns_context(make_user: MakeUser) -> None:
    email, department_ids = await make_user("dept_manager", with_department=True)
    current = await _current_session_for(email)
    ctx = RequestContext(ip=None, user_agent="pytest", trace_id=uuid4().hex)

    authorize = authz.Authorize("contracts:read")
    async with session_factory() as session:
        result = await authorize(current=current, session=session, ctx=ctx)

    assert result.access == authz.Access.DEPT
    assert result.scope.type == "departments"
    assert result.scope.department_ids == department_ids


async def test_view_all_rejected_for_employee_and_audited(make_user: MakeUser) -> None:
    email, _ = await make_user("employee")
    current = await _current_session_for(email)
    ctx = RequestContext(ip=None, user_agent="pytest", trace_id=uuid4().hex)

    async with session_factory() as session:
        with pytest.raises(Problem) as excinfo:
            await authz.resolve_view_scope(session, current.user, "all", ctx)

    assert excinfo.value.status_code == 403

    denial = await _last_denial(current.user.id)
    assert denial is not None
    assert denial["resource_id"] == "view:all"


async def test_view_all_allowed_for_admin(make_user: MakeUser) -> None:
    email, _ = await make_user("admin")
    current = await _current_session_for(email)
    ctx = RequestContext(ip=None, user_agent="pytest", trace_id=uuid4().hex)

    async with session_factory() as session:
        scope = await authz.resolve_view_scope(session, current.user, "all", ctx)

    assert scope.type == "all"
