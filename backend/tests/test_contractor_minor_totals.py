"""Estat econòmic en menors per adjudicatari (specs/contractor-economic-status.md)."""

import uuid as uuid_module

import pytest
from sqlalchemy import text

from app.core.db import session_factory
from tests.conftest import login_headers

pytestmark = pytest.mark.anyio


async def test_minor_totals_by_year_and_type(api_client, make_user) -> None:  # type: ignore[no-untyped-def]
    tag = uuid_module.uuid4().hex[:8]
    employee = await make_user("employee")  # tothom hi ha de poder accedir

    async with session_factory() as session:
        contractor = (
            await session.execute(
                text(
                    "INSERT INTO contractors (canonical_name, tax_id) VALUES (:n, :t) RETURNING id"
                ),
                {"n": f"Proveïdor {tag}", "t": f"B{tag[:8].upper()}"},
            )
        ).scalar_one()
        rows = [
            (f"MIN-{tag}/1", "Obres", 30000, 2026),
            (f"MIN-{tag}/2", "Obres", 15000, 2026),
            (f"MIN-{tag}/3", "Serveis", 1000, 2026),
            (f"MIN-{tag}/4", "Serveis", 5000, 2025),
        ]
        for file_code, contract_type, amount, year in rows:
            await session.execute(
                text(
                    "INSERT INTO minor_contracts (file_code, contract_type, award_amount, "
                    "fiscal_year, contractor_id) VALUES (:f, :t, :a, :y, :c)"
                ),
                {"f": file_code, "t": contract_type, "a": amount, "y": year, "c": contractor},
            )
        await session.commit()

    try:
        headers = login_headers(api_client, employee.email)
        response = api_client.get(f"/api/v1/contractors/{contractor}/minor-totals", headers=headers)
        assert response.status_code == 200, response.text
        data = response.json()["data"]

        assert [y["fiscal_year"] for y in data] == [2026, 2025], "més recent primer"
        year_2026 = data[0]
        assert year_2026["count"] == 3
        assert float(year_2026["amount"]) == 46000.0
        by_type = {row["contract_type"]: row for row in year_2026["by_type"]}
        assert float(by_type["Obres"]["amount"]) == 45000.0
        assert by_type["Obres"]["count"] == 2
        assert float(by_type["Serveis"]["amount"]) == 1000.0
        assert float(data[1]["amount"]) == 5000.0

        assert (
            api_client.get("/api/v1/contractors/99999999/minor-totals", headers=headers).status_code
            == 404
        )
    finally:
        async with session_factory() as session:
            await session.execute(
                text("DELETE FROM minor_contracts WHERE file_code LIKE :p"), {"p": f"MIN-{tag}%"}
            )
            await session.execute(text("DELETE FROM contractors WHERE id = :c"), {"c": contractor})
            await session.commit()
