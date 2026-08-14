"""Motor de regles LCSP (specs/compliance-rules.md)."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.core.db import session_factory
from app.modules.compliance import engine
from tests.conftest import login_headers

pytestmark = pytest.mark.anyio

TODAY = date(2026, 8, 15)


def test_minor_thresholds_by_type() -> None:
    over = engine.check_minor(
        contract_type="Serveis", award_amount=Decimal("15000.01"),
        duration_years=0, duration_months=6, when=TODAY,
    )
    assert engine.worst_status(over) == "no_conforme"
    works_ok = engine.check_minor(
        contract_type="Obres", award_amount=Decimal("39999.99"),
        duration_years=1, duration_months=0, when=TODAY,
    )
    assert engine.worst_status(works_ok) == "conforme"
    too_long = engine.check_minor(
        contract_type="Serveis", award_amount=Decimal("1000"),
        duration_years=1, duration_months=1, when=TODAY,
    )
    assert engine.worst_status(too_long) == "no_conforme"
    unknown = engine.check_minor(
        contract_type="Serveis", award_amount=None,
        duration_years=None, duration_months=None, when=TODAY,
    )
    assert engine.worst_status(unknown) == "no_verificable"


def test_plan_entry_threshold() -> None:
    warn = engine.check_plan_entry(
        contract_type="Serveis", estimated_amount=Decimal("20000"), fiscal_year=2026
    )
    assert engine.worst_status(warn) == "avis"
    ok = engine.check_plan_entry(
        contract_type="Obres", estimated_amount=Decimal("20000"), fiscal_year=2026
    )
    assert engine.worst_status(ok) == "conforme"


def test_rule_versioning_by_date() -> None:
    assert engine.rule_for("minor.amount", date(2017, 1, 1)) is None
    assert engine.rule_for("minor.amount", date(2020, 1, 1)) is not None


async def test_compliance_api(api_client, make_user) -> None:  # type: ignore[no-untyped-def]
    admin_user = await make_user("admin")
    employee = await make_user("employee")
    admin = login_headers(api_client, admin_user.email)

    # employee sense compliance:run → 403.
    assert (
        api_client.get(
            "/api/v1/compliance/rules", headers=login_headers(api_client, employee.email)
        ).status_code
        == 403
    )
    rules = api_client.get("/api/v1/compliance/rules", headers=admin)
    assert rules.status_code == 200
    assert any(r["rule_id"] == "minor.amount" for r in rules.json()["data"])

    # Entrada de pla sobre llindar → avis + review persistida.
    created = api_client.post(
        "/api/v1/plan",
        json={
            "fiscal_year": 2099, "quarter": 1,
            "subject": "Servei gran de prova compliance", "contract_type": "Serveis",
            "estimated_amount": 20000,
        },
        headers=admin,
    )
    entry_id = created.json()["id"]
    check = api_client.post(
        "/api/v1/compliance/check",
        json={"subject_type": "plan_entry", "subject_id": entry_id},
        headers=admin,
    )
    assert check.status_code == 200, check.text
    assert check.json()["status"] == "avis"

    batch = api_client.post(
        "/api/v1/compliance/check-plan", json={"fiscal_year": 2099}, headers=admin
    )
    assert batch.status_code == 200
    row = next(r for r in batch.json()["data"] if r["entry_id"] == entry_id)
    assert row["status"] == "avis"

    async with session_factory() as session:
        count = (
            await session.execute(
                text(
                    "SELECT count(*) FROM compliance_reviews "
                    "WHERE subject_type = 'plan_entry' AND subject_id = :i"
                ),
                {"i": entry_id},
            )
        ).scalar_one()
    assert count >= 2

    assert (
        api_client.post(
            "/api/v1/compliance/check",
            json={"subject_type": "minor_contract", "subject_id": 999999999},
            headers=admin,
        ).status_code
        == 404
    )
    api_client.delete(f"/api/v1/plan/{entry_id}", headers=admin)
