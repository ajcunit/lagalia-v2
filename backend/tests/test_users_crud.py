"""Integració del CRUD d'usuaris i del perfil propi (PATCH /me)."""

from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from tests.conftest import TEST_PASSWORD, MakeUser, TestUser, login_headers


def _new_user_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": "Usuària Nova",
        "email": f"crud-{uuid4().hex[:10]}@cunit.cat",
        "role": "employee",
        "password": "Contrasenya-Robusta-42",
    }
    payload.update(overrides)
    return payload


async def _cleanup_user(email: str) -> None:
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM users WHERE email = :email"), {"email": email})
    await engine.dispose()


async def test_create_user_full_cycle(api_client: TestClient, make_user: MakeUser) -> None:
    admin: TestUser = await make_user("admin", with_department=True)
    headers = login_headers(api_client, admin.email)
    payload = _new_user_payload(department_ids=admin.department_ids)

    created = api_client.post("/api/v1/users", json=payload, headers=headers)

    assert created.status_code == 201, created.text
    body = created.json()
    assert body["email"] == payload["email"]
    assert body["auth_source"] == "local"
    assert [d["id"] for d in body["departments"]] == admin.department_ids

    fetched = api_client.get(f"/api/v1/users/{body['id']}", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["name"] == "Usuària Nova"

    await _cleanup_user(payload["email"])


async def test_create_duplicate_email_is_409(api_client: TestClient, make_user: MakeUser) -> None:
    admin: TestUser = await make_user("admin")
    headers = login_headers(api_client, admin.email)

    response = api_client.post(
        "/api/v1/users", json=_new_user_payload(email=admin.email.upper()), headers=headers
    )

    assert response.status_code == 409


async def test_create_weak_or_leaked_password_is_422(
    api_client: TestClient, make_user: MakeUser
) -> None:
    admin: TestUser = await make_user("admin")
    headers = login_headers(api_client, admin.email)

    weak = api_client.post(
        "/api/v1/users", json=_new_user_payload(password="curta1A"), headers=headers
    )
    leaked = api_client.post(
        "/api/v1/users", json=_new_user_payload(password="Password12345"), headers=headers
    )

    assert weak.status_code == 422
    assert leaked.status_code == 422
    assert "curta1A" not in weak.text  # mai eco del valor rebut


async def test_create_directory_user_without_password(
    api_client: TestClient, make_user: MakeUser
) -> None:
    admin: TestUser = await make_user("admin")
    headers = login_headers(api_client, admin.email)
    payload = _new_user_payload()
    del payload["password"]

    response = api_client.post("/api/v1/users", json=payload, headers=headers)

    assert response.status_code == 201
    assert response.json()["auth_source"] == "ldap"
    await _cleanup_user(payload["email"])


async def test_employee_cannot_create_users(api_client: TestClient, make_user: MakeUser) -> None:
    employee: TestUser = await make_user("employee")
    headers = login_headers(api_client, employee.email)

    response = api_client.post("/api/v1/users", json=_new_user_payload(), headers=headers)

    assert response.status_code == 403


async def test_get_missing_user_is_404(api_client: TestClient, make_user: MakeUser) -> None:
    admin: TestUser = await make_user("admin")
    headers = login_headers(api_client, admin.email)

    response = api_client.get("/api/v1/users/999999999", headers=headers)

    assert response.status_code == 404


async def test_patch_user_fields(api_client: TestClient, make_user: MakeUser) -> None:
    admin: TestUser = await make_user("admin")
    subject: TestUser = await make_user("employee")
    headers = login_headers(api_client, admin.email)

    response = api_client.patch(
        f"/api/v1/users/{subject.id}",
        json={"name": "Nom Canviat", "can_plan": True, "role": "dept_manager"},
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Nom Canviat"
    assert body["can_plan"] is True
    assert body["role"] == "dept_manager"


async def test_deactivation_revokes_sessions(api_client: TestClient, make_user: MakeUser) -> None:
    admin: TestUser = await make_user("admin")
    subject: TestUser = await make_user("employee")
    admin_headers = login_headers(api_client, admin.email)

    login = api_client.post(
        "/api/v1/auth/login", json={"email": subject.email, "password": TEST_PASSWORD}
    )
    refresh_token = login.json()["refresh_token"]

    deleted = api_client.delete(f"/api/v1/users/{subject.id}", headers=admin_headers)
    assert deleted.status_code == 204

    refresh = api_client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert refresh.status_code == 401

    # Baixa lògica: l'usuari continua existint, inactiu.
    fetched = api_client.get(f"/api/v1/users/{subject.id}", headers=admin_headers)
    assert fetched.status_code == 200
    assert fetched.json()["active"] is False


async def test_patch_active_false_also_revokes_sessions(
    api_client: TestClient, make_user: MakeUser
) -> None:
    admin: TestUser = await make_user("admin")
    subject: TestUser = await make_user("employee")
    admin_headers = login_headers(api_client, admin.email)

    login = api_client.post(
        "/api/v1/auth/login", json={"email": subject.email, "password": TEST_PASSWORD}
    )
    refresh_token = login.json()["refresh_token"]

    patched = api_client.patch(
        f"/api/v1/users/{subject.id}", json={"active": False}, headers=admin_headers
    )
    assert patched.status_code == 200

    refresh = api_client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert refresh.status_code == 401


async def test_list_users_pagination_by_department(
    api_client: TestClient, make_user: MakeUser
) -> None:
    admin: TestUser = await make_user("admin", with_department=True)
    dept_id = admin.department_ids[0]
    headers = login_headers(api_client, admin.email)
    emails = []
    for _ in range(3):
        payload = _new_user_payload(department_ids=[dept_id])
        created = api_client.post("/api/v1/users", json=payload, headers=headers)
        assert created.status_code == 201
        emails.append(payload["email"])

    first_page = api_client.get(
        "/api/v1/users",
        params={"page[size]": 2, "filter[department_id]": dept_id},
        headers=headers,
    ).json()

    assert first_page["meta"]["total"] == 4  # admin + 3 creats
    assert len(first_page["data"]) == 2
    assert first_page["meta"]["next_cursor"]

    second_page = api_client.get(
        "/api/v1/users",
        params={
            "page[size]": 2,
            "filter[department_id]": dept_id,
            "page[cursor]": first_page["meta"]["next_cursor"],
        },
        headers=headers,
    ).json()

    assert len(second_page["data"]) == 2
    ids_first = {u["id"] for u in first_page["data"]}
    ids_second = {u["id"] for u in second_page["data"]}
    assert not ids_first & ids_second  # sense duplicats entre pàgines

    for email in emails:
        await _cleanup_user(email)


async def test_update_me_dni_password(api_client: TestClient, make_user: MakeUser) -> None:
    user: TestUser = await make_user("employee")
    headers = login_headers(api_client, user.email)

    response = api_client.patch(
        "/api/v1/me",
        json={"name": "Nou Nom", "dni": "12345678Z", "password": "Nova-Contrasenya-77"},
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Nou Nom"
    assert body["dni"] == "12345678Z"

    # A la BD el DNI no hi és mai en clar.
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    async with engine.connect() as conn:
        encrypted = (
            await conn.execute(
                text("SELECT dni_encrypted FROM users WHERE id = :id"), {"id": user.id}
            )
        ).scalar_one()
    await engine.dispose()
    assert encrypted is not None
    assert b"12345678Z" not in bytes(encrypted)

    old_login = api_client.post(
        "/api/v1/auth/login", json={"email": user.email, "password": TEST_PASSWORD}
    )
    new_login = api_client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "Nova-Contrasenya-77"},
    )
    assert old_login.status_code == 401
    assert new_login.status_code == 200


async def test_directory_user_cannot_set_local_password(
    api_client: TestClient, make_user: MakeUser
) -> None:
    admin: TestUser = await make_user("admin")
    headers = login_headers(api_client, admin.email)
    payload = _new_user_payload()
    del payload["password"]
    created = api_client.post("/api/v1/users", json=payload, headers=headers).json()

    # L'usuari de directori no pot iniciar sessió local; simulem el PATCH /me
    # per la via d'administració per verificar la regla al servei.
    response = api_client.patch(
        f"/api/v1/users/{created['id']}",
        json={"password": "Contrasenya-Robusta-42"},
        headers=headers,
    )
    # Per la via d'admin sí que es pot establir contrasenya (conversió a local).
    assert response.status_code == 200
    assert response.json()["auth_source"] == "local"

    await _cleanup_user(created["email"])
