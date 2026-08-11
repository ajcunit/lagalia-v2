"""Integració del CRUD de departaments."""

from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from tests.conftest import MakeUser, TestUser, login_headers


def _payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "code": f"DEP-{uuid4().hex[:8]}",
        "name": "Departament de Proves",
        "description": "Creat pels tests d'integració",
    }
    payload.update(overrides)
    return payload


async def _cleanup_department(code: str) -> None:
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM departments WHERE code = :code"), {"code": code})
    await engine.dispose()


async def test_department_full_cycle(api_client: TestClient, make_user: MakeUser) -> None:
    admin: TestUser = await make_user("admin")
    headers = login_headers(api_client, admin.email)
    payload = _payload()

    created = api_client.post("/api/v1/departments", json=payload, headers=headers)
    assert created.status_code == 201, created.text
    dept = created.json()
    assert dept["code"] == payload["code"]
    assert dept["active"] is True
    assert dept["gestiona_group"] is None

    updated = api_client.patch(
        f"/api/v1/departments/{dept['id']}", json={"name": "Nom Nou"}, headers=headers
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Nom Nou"

    deleted = api_client.delete(f"/api/v1/departments/{dept['id']}", headers=headers)
    assert deleted.status_code == 204

    fetched = api_client.get(f"/api/v1/departments/{dept['id']}", headers=headers)
    assert fetched.status_code == 200  # baixa lògica: encara existeix
    assert fetched.json()["active"] is False

    await _cleanup_department(payload["code"])


async def test_duplicate_code_is_409(api_client: TestClient, make_user: MakeUser) -> None:
    admin: TestUser = await make_user("admin")
    headers = login_headers(api_client, admin.email)
    payload = _payload()
    first = api_client.post("/api/v1/departments", json=payload, headers=headers)
    assert first.status_code == 201

    second = api_client.post(
        "/api/v1/departments", json=_payload(code=payload["code"]), headers=headers
    )

    assert second.status_code == 409
    await _cleanup_department(payload["code"])


async def test_employee_can_read_but_not_write(api_client: TestClient, make_user: MakeUser) -> None:
    employee: TestUser = await make_user("employee", with_department=True)
    headers = login_headers(api_client, employee.email)

    listed = api_client.get("/api/v1/departments", headers=headers)
    assert listed.status_code == 200

    created = api_client.post("/api/v1/departments", json=_payload(), headers=headers)
    assert created.status_code == 403


async def test_department_users_listing(api_client: TestClient, make_user: MakeUser) -> None:
    admin: TestUser = await make_user("admin")
    member: TestUser = await make_user("employee", with_department=True)
    headers = login_headers(api_client, admin.email)
    dept_id = member.department_ids[0]

    response = api_client.get(f"/api/v1/departments/{dept_id}/users", headers=headers)

    assert response.status_code == 200
    emails = [u["email"] for u in response.json()["data"]]
    assert member.email in emails

    missing = api_client.get("/api/v1/departments/999999999/users", headers=headers)
    assert missing.status_code == 404


async def test_list_departments_filter_active(api_client: TestClient, make_user: MakeUser) -> None:
    admin: TestUser = await make_user("admin")
    headers = login_headers(api_client, admin.email)
    payload = _payload()
    created = api_client.post("/api/v1/departments", json=payload, headers=headers).json()
    api_client.delete(f"/api/v1/departments/{created['id']}", headers=headers)

    inactive = api_client.get(
        "/api/v1/departments", params={"filter[active]": False}, headers=headers
    ).json()

    assert created["id"] in [d["id"] for d in inactive["data"]]
    await _cleanup_department(payload["code"])
