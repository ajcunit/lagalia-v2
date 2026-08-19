"""Pla anual (specs/annual-plan.md)."""

import pytest

from tests.conftest import login_headers

pytestmark = pytest.mark.anyio


async def test_plan_workflow(api_client, make_user) -> None:  # type: ignore[no-untyped-def]
    admin_user = await make_user("admin")
    planner = await make_user("employee", can_plan=True)
    outsider = await make_user("employee")
    admin = login_headers(api_client, admin_user.email)
    plan = login_headers(api_client, planner.email)

    # Sense can_plan → 403.
    assert (
        api_client.get(
            "/api/v1/plan",
            params={"fiscal_year": 2026},
            headers=login_headers(api_client, outsider.email),
        ).status_code
        == 403
    )

    # No-admin crea en pending; admin en approved.
    body = {"fiscal_year": 2026, "quarter": 2, "subject": "Servei de neteja de platges"}
    mine = api_client.post("/api/v1/plan", json=body, headers=plan)
    assert mine.status_code == 201, mine.text
    assert mine.json()["status"] == "pending"
    theirs = api_client.post("/api/v1/plan", json={**body, "quarter": 3}, headers=admin)
    assert theirs.json()["status"] == "approved"

    entry_id = mine.json()["id"]
    # Aprovar: planner no pot; admin sí.
    assert (
        api_client.post(f"/api/v1/plan/{entry_id}/actions/approve", headers=plan).status_code == 403
    )
    approved = api_client.post(f"/api/v1/plan/{entry_id}/actions/approve", headers=admin)
    assert approved.json()["status"] == "approved"

    # Editar una aprovada com a no-admin → torna a pending.
    edited = api_client.patch(f"/api/v1/plan/{entry_id}", json={"notes": "canvi"}, headers=plan)
    assert edited.json()["status"] == "pending"

    # Llistat per exercici i esborrat (autor).
    listing = api_client.get("/api/v1/plan", params={"fiscal_year": 2026}, headers=plan)
    assert {e["id"] for e in listing.json()["data"]} >= {entry_id, theirs.json()["id"]}
    assert api_client.delete(f"/api/v1/plan/{entry_id}", headers=plan).status_code == 204

    # Caduquen: respon 200 amb estructura.
    expiring = api_client.get("/api/v1/plan/expiring", params={"fiscal_year": 2026}, headers=plan)
    assert expiring.status_code == 200
    assert isinstance(expiring.json()["data"], list)
