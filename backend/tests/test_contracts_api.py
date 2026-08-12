"""API de contractes: abast departamental (anti-IDOR), edició per matriu."""

from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.db import session_factory
from tests.conftest import MakeUser, TestUser, login_headers


@pytest.fixture
async def world(make_user: MakeUser) -> AsyncIterator[dict[str, Any]]:
    """Dos departaments, un contracte assignat a A, usuaris de tots els perfils."""
    tag = uuid4().hex[:8]
    data: dict[str, Any] = {"tag": tag}

    admin: TestUser = await make_user("admin")
    manager: TestUser = await make_user("employee")  # responsable sense departament
    employee_a: TestUser = await make_user("employee")
    employee_b: TestUser = await make_user("employee")
    dm_a: TestUser = await make_user("dept_manager")
    data.update(
        admin=admin, manager=manager, employee_a=employee_a, employee_b=employee_b, dm_a=dm_a
    )

    async with session_factory() as session:
        dept_a = (
            await session.execute(
                text("INSERT INTO departments (code, name) VALUES (:c, 'A') RETURNING id"),
                {"c": f"CA-{tag}"},
            )
        ).scalar_one()
        dept_b = (
            await session.execute(
                text("INSERT INTO departments (code, name) VALUES (:c, 'B') RETURNING id"),
                {"c": f"CB-{tag}"},
            )
        ).scalar_one()
        for user_id, dept in ((employee_a.id, dept_a), (dm_a.id, dept_a), (employee_b.id, dept_b)):
            await session.execute(
                text("INSERT INTO user_departments (user_id, department_id) VALUES (:u, :d)"),
                {"u": user_id, "d": dept},
            )

        contract_a = (
            await session.execute(
                text(
                    "INSERT INTO contracts (file_code, status, lot, subject, award_amount, "
                    "published_at) VALUES (:f, 'Formalitzat', '', :s, 1000, '2026-01-01') "
                    "RETURNING id"
                ),
                {"f": f"CTR-{tag}/1", "s": f"Servei {tag} de neteja"},
            )
        ).scalar_one()
        await session.execute(
            text("INSERT INTO contract_departments (contract_id, department_id) VALUES (:c, :d)"),
            {"c": contract_a, "d": dept_a},
        )
        await session.execute(
            text("INSERT INTO contract_managers (contract_id, user_id) VALUES (:c, :u)"),
            {"c": contract_a, "u": manager.id},
        )

        orphan = (
            await session.execute(
                text(
                    "INSERT INTO contracts (file_code, status, lot, subject, published_at) "
                    "VALUES (:f, 'Adjudicat', '', :s, '2026-02-01') RETURNING id"
                ),
                {"f": f"CTR-{tag}/2", "s": f"Obra {tag} sense departament"},
            )
        ).scalar_one()
        await session.commit()
        data.update(dept_a=dept_a, dept_b=dept_b, contract_a=contract_a, orphan=orphan)

    yield data

    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.execute(
            text("DELETE FROM contracts WHERE file_code LIKE :p"), {"p": f"CTR-{tag}%"}
        )
        await conn.execute(text("DELETE FROM departments WHERE code LIKE :p"), {"p": f"C_-{tag}"})
    await engine.dispose()


def _list(client: TestClient, headers: dict[str, str], tag: str, **params: Any) -> Any:
    response = client.get("/api/v1/contracts", params={"q": tag, **params}, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


async def test_departmental_scope_on_listing(api_client: TestClient, world: dict[str, Any]) -> None:
    tag = world["tag"]

    admin_view = _list(api_client, login_headers(api_client, world["admin"].email), tag, view="all")
    assert admin_view["meta"]["total"] == 2  # ho veu tot

    a_view = _list(api_client, login_headers(api_client, world["employee_a"].email), tag)
    assert a_view["meta"]["total"] == 1
    assert a_view["data"][0]["id"] == world["contract_a"]

    b_view = _list(api_client, login_headers(api_client, world["employee_b"].email), tag)
    assert b_view["meta"]["total"] == 0

    manager_view = _list(api_client, login_headers(api_client, world["manager"].email), tag)
    assert manager_view["meta"]["total"] == 1  # responsable sense departament


async def test_idor_detail_and_subresources_are_404(
    api_client: TestClient, world: dict[str, Any]
) -> None:
    headers = login_headers(api_client, world["employee_b"].email)
    contract_id = world["contract_a"]

    subresources = (
        "",
        "/history",
        "/extensions",
        "/modifications",
        "/criteria",
        "/committee",
        "/documents",
    )
    for path in subresources:
        response = api_client.get(f"/api/v1/contracts/{contract_id}{path}", headers=headers)
        assert response.status_code == 404, f"IDOR obert a {path or '/detall'}"


async def test_enrichment_subresources_content(
    api_client: TestClient, world: dict[str, Any]
) -> None:
    contract_id = world["contract_a"]
    async with session_factory() as session:
        await session.execute(
            text(
                "INSERT INTO award_criteria (contract_id, position, name, weight, breakdown) "
                "VALUES (:c, 1, 'Preu', 50, '{\"desglossament\": []}'::jsonb), "
                "(:c, 2, 'Judici de valor', 40, NULL)"
            ),
            {"c": contract_id},
        )
        await session.execute(
            text(
                "INSERT INTO committee_members (contract_id, first_name, last_name, role) "
                "VALUES (:c, 'Anna', 'Puig Serra', 'Presidenta')"
            ),
            {"c": contract_id},
        )
        await session.execute(
            text(
                "INSERT INTO phase_documents (contract_id, phase, title, size, download_url, "
                "storage_key) VALUES "
                "(:c, 'licitacio', 'PCAP.pdf', 522847, 'https://portal/d/1', 'contracts/x/1'), "
                "(:c, 'adjudicacio', 'Acta.pdf', 1000, 'https://portal/d/2', NULL)"
            ),
            {"c": contract_id},
        )
        await session.commit()

    headers = login_headers(api_client, world["employee_a"].email)

    criteria = api_client.get(f"/api/v1/contracts/{contract_id}/criteria", headers=headers)
    assert criteria.status_code == 200
    rows = criteria.json()["data"]
    assert [r["name"] for r in rows] == ["Preu", "Judici de valor"]
    assert rows[0]["weight"] == "50.00"
    assert rows[0]["breakdown"] == {"desglossament": []}

    committee = api_client.get(f"/api/v1/contracts/{contract_id}/committee", headers=headers)
    assert committee.status_code == 200
    member = committee.json()["data"][0]
    assert member["last_name"] == "Puig Serra"
    assert member["role"] == "Presidenta"

    documents = api_client.get(f"/api/v1/contracts/{contract_id}/documents", headers=headers)
    assert documents.status_code == 200
    docs = documents.json()["data"]
    assert len(docs) == 2
    by_title = {d["title"]: d for d in docs}
    assert by_title["PCAP.pdf"]["has_copy"] is True
    assert by_title["Acta.pdf"]["has_copy"] is False
    assert by_title["PCAP.pdf"]["size"] == 522847
    # storage_key és infraestructura: mai a la resposta.
    assert "storage_key" not in by_title["PCAP.pdf"]


async def test_detail_visible_for_member_manager_and_admin(
    api_client: TestClient, world: dict[str, Any]
) -> None:
    contract_id = world["contract_a"]
    for key in ("employee_a", "manager", "admin"):
        headers = login_headers(api_client, world[key].email)
        response = api_client.get(f"/api/v1/contracts/{contract_id}", headers=headers)
        assert response.status_code == 200, key

    body = response.json()
    assert body["counters"] == {"extensions": 0, "modifications": 0, "history": 0}
    assert body["department_ids"] == [world["dept_a"]]
    assert "raw" not in body and "content_hash" not in body


async def test_admin_can_request_user_view(api_client: TestClient, world: dict[str, Any]) -> None:
    headers = login_headers(api_client, world["admin"].email)

    scoped = _list(api_client, headers, world["tag"], view="user")

    assert scoped["meta"]["total"] == 0  # l'admin no té departaments


async def test_patch_by_admin_creates_history_and_audit(
    api_client: TestClient, world: dict[str, Any]
) -> None:
    headers = login_headers(api_client, world["admin"].email)
    contract_id = world["contract_a"]

    response = api_client.patch(
        f"/api/v1/contracts/{contract_id}",
        json={"subject": "Objecte esmenat manualment", "internal_status": "approved"},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["internal_status"] == "approved"

    history = api_client.get(f"/api/v1/contracts/{contract_id}/history", headers=headers).json()
    manual = [e for e in history["data"] if e["change_type"] == "manual"]
    assert {e["field"] for e in manual} == {"subject", "internal_status"}
    assert all(e["user_id"] == world["admin"].id for e in manual)


async def test_dept_manager_can_only_touch_warning_override(
    api_client: TestClient, world: dict[str, Any]
) -> None:
    headers = login_headers(api_client, world["dm_a"].email)
    contract_id = world["contract_a"]

    allowed = api_client.patch(
        f"/api/v1/contracts/{contract_id}",
        json={"warning_months_override": 3},
        headers=headers,
    )
    assert allowed.status_code == 200
    assert allowed.json()["warning_months_override"] == 3

    forbidden = api_client.patch(
        f"/api/v1/contracts/{contract_id}",
        json={"subject": "Intent de canvi"},
        headers=headers,
    )
    assert forbidden.status_code == 403

    # Fora del seu abast: 404, ni tan sols per a l'avís.
    out_of_scope = api_client.patch(
        f"/api/v1/contracts/{world['orphan']}",
        json={"warning_months_override": 3},
        headers=headers,
    )
    assert out_of_scope.status_code == 404


async def test_employee_cannot_patch(api_client: TestClient, world: dict[str, Any]) -> None:
    headers = login_headers(api_client, world["employee_a"].email)

    response = api_client.patch(
        f"/api/v1/contracts/{world['contract_a']}",
        json={"warning_months_override": 2},
        headers=headers,
    )

    assert response.status_code == 403


async def test_manual_creation(api_client: TestClient, world: dict[str, Any]) -> None:
    tag = world["tag"]
    headers = login_headers(api_client, world["admin"].email)
    payload = {
        "file_code": f"CTR-{tag}/NOU",
        "subject": f"Contracte manual {tag}",
        "contract_type": "Serveis",
        "department_ids": [world["dept_a"]],
    }

    created = api_client.post("/api/v1/contracts", json=payload, headers=headers)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["source"] == "local"
    assert body["department_ids"] == [world["dept_a"]]

    duplicate = api_client.post("/api/v1/contracts", json=payload, headers=headers)
    assert duplicate.status_code == 409

    employee = api_client.post(
        "/api/v1/contracts",
        json=payload,
        headers=login_headers(api_client, world["employee_a"].email),
    )
    assert employee.status_code == 403


async def test_filters_and_sort(api_client: TestClient, world: dict[str, Any]) -> None:
    tag = world["tag"]
    headers = login_headers(api_client, world["admin"].email)

    unassigned = _list(api_client, headers, tag, view="all", **{"filter[unassigned]": True})
    assert unassigned["meta"]["total"] == 1
    assert unassigned["data"][0]["id"] == world["orphan"]

    by_dept = _list(
        api_client, headers, tag, view="all", **{"filter[department_id]": world["dept_a"]}
    )
    assert by_dept["meta"]["total"] == 1

    by_year = _list(api_client, headers, tag, view="all", **{"filter[year]": 2026})
    assert by_year["meta"]["total"] == 2

    ordered = _list(api_client, headers, tag, view="all", sort="file_code")
    codes = [c["file_code"] for c in ordered["data"]]
    assert codes == sorted(codes)

    bad_sort = api_client.get("/api/v1/contracts", params={"sort": "malicios"}, headers=headers)
    assert bad_sort.status_code == 422
