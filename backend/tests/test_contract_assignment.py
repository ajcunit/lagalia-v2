"""Assignació individual de departaments i responsables
(specs/contract-assignment.md)."""

import uuid as uuid_module

import pytest
from sqlalchemy import text

from app.core.db import session_factory
from tests.conftest import login_headers

pytestmark = pytest.mark.anyio


@pytest.fixture
async def assign_world(make_user):  # type: ignore[no-untyped-def]
    tag = uuid_module.uuid4().hex[:8]
    admin = await make_user("admin")
    employee = await make_user("employee")
    manager_user = await make_user("employee")

    async with session_factory() as session:
        dept_a = (
            await session.execute(
                text("INSERT INTO departments (code, name) VALUES (:c, 'AsgA') RETURNING id"),
                {"c": f"AS-A-{tag}"},
            )
        ).scalar_one()
        dept_b = (
            await session.execute(
                text("INSERT INTO departments (code, name) VALUES (:c, 'AsgB') RETURNING id"),
                {"c": f"AS-B-{tag}"},
            )
        ).scalar_one()
        contract = (
            await session.execute(
                text(
                    "INSERT INTO contracts (file_code, status, lot, subject, published_at) "
                    "VALUES (:f, 'Formalitzat', '', :s, '2026-01-01') RETURNING id"
                ),
                {"f": f"ASG-{tag}/1", "s": f"Servei {tag} per assignar"},
            )
        ).scalar_one()
        await session.commit()

    yield {
        "tag": tag,
        "admin": admin,
        "employee": employee,
        "manager_user": manager_user,
        "dept_a": dept_a,
        "dept_b": dept_b,
        "contract": contract,
    }

    async with session_factory() as session:
        await session.execute(
            text("DELETE FROM contracts WHERE file_code LIKE :p"), {"p": f"ASG-{tag}%"}
        )
        await session.execute(
            text("DELETE FROM departments WHERE code LIKE :p"), {"p": f"AS-_-{tag}"}
        )
        await session.commit()


def _assign(client, headers, contract_id, department_ids, manager_ids):  # type: ignore[no-untyped-def]
    return client.put(
        f"/api/v1/contracts/{contract_id}/assignments",
        json={"department_ids": department_ids, "manager_ids": manager_ids},
        headers=headers,
    )


async def test_assign_departments_and_managers(api_client, assign_world) -> None:  # type: ignore[no-untyped-def]
    w = assign_world
    headers = login_headers(api_client, w["admin"].email)

    response = _assign(
        api_client, headers, w["contract"], [w["dept_a"], w["dept_b"]], [w["manager_user"].id]
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert sorted(body["department_ids"]) == sorted([w["dept_a"], w["dept_b"]])
    assert [m["id"] for m in body["managers"]] == [w["manager_user"].id]

    # Historial per als dos camps i auditoria contracts.assign.
    async with session_factory() as session:
        fields = {
            row.field
            for row in (
                await session.execute(
                    text("SELECT field FROM contract_history WHERE contract_id = :c"),
                    {"c": w["contract"]},
                )
            ).all()
        }
        audited = (
            await session.execute(
                text(
                    "SELECT count(*) FROM audit_log WHERE action = 'contracts.assign' "
                    "AND resource_id = :r"
                ),
                {"r": str(w["contract"])},
            )
        ).scalar_one()
    assert {"departments", "managers"} <= fields
    assert audited >= 1

    # El responsable acabat d'assignar (sense departament) ja veu el contracte.
    manager_headers = login_headers(api_client, w["manager_user"].email)
    visible = api_client.get(f"/api/v1/contracts/{w['contract']}", headers=manager_headers)
    assert visible.status_code == 200

    # Substitució sencera: treure un departament i tots els responsables.
    response = _assign(api_client, headers, w["contract"], [w["dept_a"]], [])
    assert response.status_code == 200
    body = response.json()
    assert body["department_ids"] == [w["dept_a"]]
    assert body["managers"] == []


async def test_assign_validates_and_denies(api_client, assign_world) -> None:  # type: ignore[no-untyped-def]
    w = assign_world
    admin_headers = login_headers(api_client, w["admin"].email)

    assert _assign(api_client, admin_headers, w["contract"], [999999], []).status_code == 422
    assert _assign(api_client, admin_headers, w["contract"], [], [999999]).status_code == 422
    assert _assign(api_client, admin_headers, 999999, [], []).status_code == 404

    employee_headers = login_headers(api_client, w["employee"].email)
    assert _assign(api_client, employee_headers, w["contract"], [], []).status_code == 403


async def test_user_options_requires_assign_grant(api_client, assign_world) -> None:  # type: ignore[no-untyped-def]
    w = assign_world
    admin_headers = login_headers(api_client, w["admin"].email)
    response = api_client.get("/api/v1/users/options", headers=admin_headers)
    assert response.status_code == 200, response.text
    rows = response.json()["data"]
    assert all(set(row) == {"id", "name"} for row in rows), "només id i nom, res més"
    assert any(row["id"] == w["manager_user"].id for row in rows)

    employee_headers = login_headers(api_client, w["employee"].email)
    assert api_client.get("/api/v1/users/options", headers=employee_headers).status_code == 403
