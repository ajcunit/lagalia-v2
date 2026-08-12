"""APIs de menors (abast), rànquing d'adjudicataris i resolució de duplicats."""

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
    """Departament amb un menor assignat, un menor orfe, i un adjudicatari
    amb 1 major + 2 menors per al rànquing."""
    tag = uuid4().hex[:8]
    data: dict[str, Any] = {"tag": tag}

    admin: TestUser = await make_user("admin")
    employee_a: TestUser = await make_user("employee")
    employee_b: TestUser = await make_user("employee")
    data.update(admin=admin, employee_a=employee_a, employee_b=employee_b)

    async with session_factory() as session:
        dept_a = (
            await session.execute(
                text("INSERT INTO departments (code, name) VALUES (:c, 'MA') RETURNING id"),
                {"c": f"MA-{tag}"},
            )
        ).scalar_one()
        dept_b = (
            await session.execute(
                text("INSERT INTO departments (code, name) VALUES (:c, 'MB') RETURNING id"),
                {"c": f"MB-{tag}"},
            )
        ).scalar_one()
        await session.execute(
            text("INSERT INTO user_departments (user_id, department_id) VALUES (:u, :d)"),
            {"u": employee_a.id, "d": dept_a},
        )
        await session.execute(
            text("INSERT INTO user_departments (user_id, department_id) VALUES (:u, :d)"),
            {"u": employee_b.id, "d": dept_b},
        )

        contractor = (
            await session.execute(
                text(
                    "INSERT INTO contractors (canonical_name, tax_id) VALUES (:n, :t) RETURNING id"
                ),
                {"n": f"Rànquing {tag} SL", "t": f"R{tag.upper()[:7]}1"},
            )
        ).scalar_one()
        twin = (
            await session.execute(
                text(
                    "INSERT INTO contractors (canonical_name, tax_id) VALUES (:n, :t) RETURNING id"
                ),
                {"n": f"RANQUING {tag}, S.L.", "t": f"R{tag.upper()[:7]}1"},
            )
        ).scalar_one()
        pair = (
            await session.execute(
                text(
                    "INSERT INTO contractor_duplicates (contractor_id_1, contractor_id_2) "
                    "VALUES (:a, :b) RETURNING id"
                ),
                {"a": min(contractor, twin), "b": max(contractor, twin)},
            )
        ).scalar_one()

        await session.execute(
            text(
                "INSERT INTO contracts (file_code, status, lot, subject, award_amount, "
                "contractor_id) VALUES (:f, 'Formalitzat', '', 'Servei major', 1000, :c)"
            ),
            {"f": f"MJR-{tag}/1", "c": contractor},
        )
        minor_a = (
            await session.execute(
                text(
                    "INSERT INTO minor_contracts (file_code, description, award_amount, "
                    "award_date, fiscal_year, contractor_id) "
                    "VALUES (:f, :d, 200, '2026-03-01', 2026, :c) RETURNING id"
                ),
                {"f": f"MNR-{tag}/1", "d": f"Menor {tag} del dept A", "c": contractor},
            )
        ).scalar_one()
        await session.execute(
            text(
                "INSERT INTO minor_contract_departments (minor_contract_id, department_id) "
                "VALUES (:m, :d)"
            ),
            {"m": minor_a, "d": dept_a},
        )
        orphan = (
            await session.execute(
                text(
                    "INSERT INTO minor_contracts (file_code, description, award_amount, "
                    "award_date, fiscal_year, contractor_id, settlement_date) "
                    "VALUES (:f, :d, 300, '2026-04-01', 2026, :c, '2026-06-01') RETURNING id"
                ),
                {"f": f"MNR-{tag}/2", "d": f"Menor {tag} orfe", "c": twin},
            )
        ).scalar_one()
        await session.commit()
        data.update(
            dept_a=dept_a,
            dept_b=dept_b,
            contractor=contractor,
            twin=twin,
            pair=pair,
            minor_a=minor_a,
            orphan=orphan,
        )

    yield data

    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.execute(
            text("DELETE FROM minor_contracts WHERE file_code LIKE :p"), {"p": f"MNR-{tag}%"}
        )
        await conn.execute(
            text("DELETE FROM contracts WHERE file_code LIKE :p"), {"p": f"MJR-{tag}%"}
        )
        await conn.execute(
            text(
                "DELETE FROM contractor_duplicates WHERE contractor_id_1 IN "
                "(SELECT id FROM contractors WHERE tax_id LIKE :t) OR contractor_id_2 IN "
                "(SELECT id FROM contractors WHERE tax_id LIKE :t)"
            ),
            {"t": f"R{tag.upper()[:7]}%"},
        )
        await conn.execute(
            text("DELETE FROM contractor_aliases WHERE alias ILIKE :p"), {"p": f"%{tag}%"}
        )
        await conn.execute(
            text("DELETE FROM contractors WHERE tax_id LIKE :t"),
            {"t": f"R{tag.upper()[:7]}%"},
        )
        await conn.execute(text("DELETE FROM departments WHERE code LIKE :p"), {"p": f"M_-{tag}"})
    await engine.dispose()


async def test_minor_scope_listing_and_idor(api_client: TestClient, world: dict[str, Any]) -> None:
    tag = world["tag"]

    admin_view = api_client.get(
        "/api/v1/minor-contracts",
        params={"q": tag, "view": "all"},
        headers=login_headers(api_client, world["admin"].email),
    ).json()
    assert admin_view["meta"]["total"] == 2

    a_headers = login_headers(api_client, world["employee_a"].email)
    a_view = api_client.get("/api/v1/minor-contracts", params={"q": tag}, headers=a_headers).json()
    assert a_view["meta"]["total"] == 1
    assert a_view["data"][0]["id"] == world["minor_a"]

    detail_ok = api_client.get(f"/api/v1/minor-contracts/{world['minor_a']}", headers=a_headers)
    assert detail_ok.status_code == 200
    assert detail_ok.json()["department_ids"] == [world["dept_a"]]

    b_headers = login_headers(api_client, world["employee_b"].email)
    idor = api_client.get(f"/api/v1/minor-contracts/{world['minor_a']}", headers=b_headers)
    assert idor.status_code == 404


async def test_minor_settled_filter(api_client: TestClient, world: dict[str, Any]) -> None:
    headers = login_headers(api_client, world["admin"].email)

    settled = api_client.get(
        "/api/v1/minor-contracts",
        params={"q": world["tag"], "view": "all", "filter[settled]": True},
        headers=headers,
    ).json()

    assert settled["meta"]["total"] == 1
    assert settled["data"][0]["id"] == world["orphan"]


async def test_minor_patch_departments_and_audit(
    api_client: TestClient, world: dict[str, Any]
) -> None:
    headers = login_headers(api_client, world["admin"].email)

    updated = api_client.patch(
        f"/api/v1/minor-contracts/{world['orphan']}",
        json={"department_ids": [world["dept_b"]], "internal_status": "approved"},
        headers=headers,
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["department_ids"] == [world["dept_b"]]
    assert body["internal_status"] == "approved"

    employee = api_client.patch(
        f"/api/v1/minor-contracts/{world['orphan']}",
        json={"internal_status": "normal"},
        headers=login_headers(api_client, world["employee_b"].email),
    )
    assert employee.status_code == 403


async def test_contractor_ranking_and_search(api_client: TestClient, world: dict[str, Any]) -> None:
    headers = login_headers(api_client, world["admin"].email)
    tag = world["tag"]

    by_name = api_client.get(
        "/api/v1/contractors", params={"q": f"Rànquing {tag}"}, headers=headers
    ).json()
    entry = next(e for e in by_name["data"] if e["id"] == world["contractor"])
    assert entry["contracts_count"] == 1
    assert entry["minor_count"] == 1
    assert entry["total_amount"] == "1200.00"  # 1000 major + 200 menor

    by_nif = api_client.get(
        "/api/v1/contractors", params={"q": f"R{tag.upper()[:7]}1"}, headers=headers
    ).json()
    assert by_nif["meta"]["total"] == 2  # els dos bessons comparteixen NIF

    profile = api_client.get(f"/api/v1/contractors/{world['contractor']}", headers=headers).json()
    assert profile["name"] == f"Rànquing {tag} SL"
    assert profile["total_amount"] == "1200.00"


async def test_duplicate_merge_full_flow(api_client: TestClient, world: dict[str, Any]) -> None:
    headers = login_headers(api_client, world["admin"].email)
    tag = world["tag"]
    first_is_contractor = min(world["contractor"], world["twin"]) == world["contractor"]
    action = "merge_1" if first_is_contractor else "merge_2"

    listed = api_client.get("/api/v1/contractors/duplicates", headers=headers).json()
    assert any(d["id"] == world["pair"] for d in listed["data"])

    resolved = api_client.post(
        f"/api/v1/contractors/duplicates/{world['pair']}/actions/resolve",
        json={"action": action, "notes": "mateixa empresa"},
        headers=headers,
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["status"] == "merged"

    # El perdedor ja no existeix; el menor orfe s'ha reassignat al guanyador.
    gone = api_client.get(f"/api/v1/contractors/{world['twin']}", headers=headers)
    assert gone.status_code == 404
    profile = api_client.get(f"/api/v1/contractors/{world['contractor']}", headers=headers).json()
    assert profile["minor_count"] == 2
    assert profile["total_amount"] == "1500.00"
    assert f"RANQUING {tag}, S.L." in profile["aliases"]

    # Segona resolució del mateix parell: ja no hi és (esborrat en cascada).
    again = api_client.post(
        f"/api/v1/contractors/duplicates/{world['pair']}/actions/resolve",
        json={"action": action},
        headers=headers,
    )
    assert again.status_code == 404

    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    async with engine.connect() as conn:
        audit = (
            await conn.execute(
                text(
                    "SELECT count(*) FROM audit_log WHERE action = 'contractors.merge' "
                    "AND resource_id = :r"
                ),
                {"r": str(world["contractor"])},
            )
        ).scalar_one()
    await engine.dispose()
    assert audit == 1


async def test_duplicate_reject_persists_and_blocks_regeneration(
    api_client: TestClient, world: dict[str, Any]
) -> None:
    headers = login_headers(api_client, world["admin"].email)

    rejected = api_client.post(
        f"/api/v1/contractors/duplicates/{world['pair']}/actions/resolve",
        json={"action": "reject"},
        headers=headers,
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"

    # La re-detecció no reobre el parell rebutjat.
    from app.modules.contractors.service import detect_tax_id_duplicates

    async with session_factory() as session:
        created = await detect_tax_id_duplicates(session)
        await session.commit()
    listed = api_client.get(
        "/api/v1/contractors/duplicates",
        params={"status": "rejected"},
        headers=headers,
    ).json()
    assert any(d["id"] == world["pair"] for d in listed["data"])
    pending = api_client.get("/api/v1/contractors/duplicates", headers=headers).json()
    assert not any(
        {d["contractor_1"]["id"], d["contractor_2"]["id"]} == {world["contractor"], world["twin"]}
        for d in pending["data"]
    )
    assert created >= 0


async def test_employee_cannot_manage_duplicates(
    api_client: TestClient, world: dict[str, Any]
) -> None:
    headers = login_headers(api_client, world["employee_a"].email)

    listed = api_client.get("/api/v1/contractors/duplicates", headers=headers)
    assert listed.status_code == 403

    resolved = api_client.post(
        f"/api/v1/contractors/duplicates/{world['pair']}/actions/resolve",
        json={"action": "reject"},
        headers=headers,
    )
    assert resolved.status_code == 403
