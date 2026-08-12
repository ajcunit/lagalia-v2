"""Stats i facets: agregacions correctes i sempre dins d'abast."""

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
from tests.conftest import login_headers


@pytest.fixture
async def world(make_user) -> AsyncIterator[dict[str, Any]]:  # type: ignore[no-untyped-def]
    tag = uuid4().hex[:8]
    data: dict[str, Any] = {"tag": tag}
    data["admin"] = await make_user("admin")
    data["employee"] = await make_user("employee")

    async with session_factory() as session:
        dept = (
            await session.execute(
                text("INSERT INTO departments (code, name) VALUES (:c, 'STA') RETURNING id"),
                {"c": f"ST-{tag}"},
            )
        ).scalar_one()
        await session.execute(
            text("INSERT INTO user_departments (user_id, department_id) VALUES (:u, :d)"),
            {"u": data["employee"].id, "d": dept},
        )
        contractor = (
            await session.execute(
                text(
                    "INSERT INTO contractors (canonical_name, tax_id) VALUES (:n, :t) RETURNING id"
                ),
                {"n": f"Contractista Stats {tag}", "t": f"B{tag[:8].upper()}"},
            )
        ).scalar_one()
        in_dept = (
            await session.execute(
                text(
                    "INSERT INTO contracts (file_code, status, lot, subject, award_amount, "
                    "published_at, contractor_id, expiry_warning) VALUES "
                    "(:f, 'StatsExec', '', :s, 1000, '2023-06-01', :co, true) RETURNING id"
                ),
                {"f": f"STA-{tag}/1", "s": f"Stats dins {tag}", "co": contractor},
            )
        ).scalar_one()
        await session.execute(
            text("INSERT INTO contract_departments (contract_id, department_id) VALUES (:c, :d)"),
            {"c": in_dept, "d": dept},
        )
        await session.execute(
            text(
                "INSERT INTO contracts (file_code, status, lot, subject, award_amount, "
                "published_at, contract_type) VALUES "
                "(:f, 'StatsFora', '', :s, 5000, '2024-06-01', :ty)"
            ),
            {"f": f"STA-{tag}/2", "s": f"Stats fora {tag}", "ty": f"TipusStats-{tag}"},
        )
        await session.commit()
        data.update(dept=dept, contractor=contractor)

    yield data

    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.execute(
            text("DELETE FROM contracts WHERE file_code LIKE :p"), {"p": f"STA-{tag}%"}
        )
        await conn.execute(
            text("DELETE FROM contractors WHERE canonical_name LIKE :p"),
            {"p": f"Contractista Stats {tag}%"},
        )
        await conn.execute(text("DELETE FROM departments WHERE code LIKE :p"), {"p": f"ST-{tag}"})
    await engine.dispose()


async def test_stats_respect_scope(api_client: TestClient, world: dict[str, Any]) -> None:
    employee = login_headers(api_client, world["employee"].email)

    response = api_client.get("/api/v1/contracts/stats", headers=employee)
    assert response.status_code == 200, response.text
    stats = response.json()

    # L'employee només veu el contracte del seu departament.
    assert stats["totals"]["contracts"] == 1
    assert stats["totals"]["expiry_warning"] == 1
    assert stats["totals"]["unique_contractors"] == 1
    assert float(stats["totals"]["awarded_total"]) == 1000.0
    assert stats["by_status"] == [{"status": "StatsExec", "count": 1}]
    assert stats["by_department"][0]["name"] == "STA"
    assert stats["top_contractors"][0]["name"] == f"Contractista Stats {world['tag']}"

    # view=all sense dret: 403 auditat.
    denied = api_client.get("/api/v1/contracts/stats", params={"view": "all"}, headers=employee)
    assert denied.status_code == 403


async def test_stats_year_filter(api_client: TestClient, world: dict[str, Any]) -> None:
    admin = login_headers(api_client, world["admin"].email)

    all_years = api_client.get(
        "/api/v1/contracts/stats", params={"view": "all"}, headers=admin
    ).json()
    only_2023 = api_client.get(
        "/api/v1/contracts/stats", params={"view": "all", "filter[year]": 2023}, headers=admin
    ).json()

    assert only_2023["totals"]["contracts"] < all_years["totals"]["contracts"]
    statuses_2023 = {s["status"] for s in only_2023["by_status"]}
    assert "StatsExec" in statuses_2023
    assert "StatsFora" not in statuses_2023  # publicat el 2024

    # Filtre d'import: només el contracte de 5000.
    amount_filtered = api_client.get(
        "/api/v1/contracts/stats",
        params={"view": "all", "filter[amount_min]": 4999, "filter[amount_max]": 5001},
        headers=admin,
    ).json()
    statuses_amount = {s["status"] for s in amount_filtered["by_status"]}
    assert "StatsFora" in statuses_amount
    assert "StatsExec" not in statuses_amount


async def test_facets_scoped_and_sorted(api_client: TestClient, world: dict[str, Any]) -> None:
    tag = world["tag"]
    employee = login_headers(api_client, world["employee"].email)
    admin = login_headers(api_client, world["admin"].email)

    employee_facets = api_client.get("/api/v1/contracts/facets", headers=employee).json()
    assert employee_facets["statuses"] == ["StatsExec"]
    assert f"TipusStats-{tag}" not in employee_facets["contract_types"]  # fora d'abast
    assert employee_facets["years"] == [2023]

    admin_facets = api_client.get(
        "/api/v1/contracts/facets", params={"view": "all"}, headers=admin
    ).json()
    assert "StatsFora" in admin_facets["statuses"]
    assert f"TipusStats-{tag}" in admin_facets["contract_types"]
    assert admin_facets["years"] == sorted(admin_facets["years"], reverse=True)
