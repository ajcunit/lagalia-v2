"""Tasques: permisos per rol, cicle d'estats, recurrència i suggeriments."""

from collections.abc import AsyncIterator
from datetime import date, timedelta
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

TODAY = date.today()


@pytest.fixture
async def world(make_user) -> AsyncIterator[dict[str, Any]]:  # type: ignore[no-untyped-def]
    """Departament amb contracte; dm dins, employee assignable, employee_out fora."""
    tag = uuid4().hex[:8]
    data: dict[str, Any] = {"tag": tag}
    data["admin"] = await make_user("admin")
    data["dm"] = await make_user("dept_manager")
    data["employee"] = await make_user("employee")
    data["employee_out"] = await make_user("employee")

    async with session_factory() as session:
        dept = (
            await session.execute(
                text("INSERT INTO departments (code, name) VALUES (:c, 'TSK') RETURNING id"),
                {"c": f"TK-{tag}"},
            )
        ).scalar_one()
        for user in (data["dm"], data["employee"]):
            await session.execute(
                text("INSERT INTO user_departments (user_id, department_id) VALUES (:u, :d)"),
                {"u": user.id, "d": dept},
            )
        contract = (
            await session.execute(
                text(
                    "INSERT INTO contracts (file_code, status, lot, subject, "
                    "calculated_end_date, expiry_warning) "
                    "VALUES (:f, 'Execució', '', :s, :d, true) RETURNING id"
                ),
                {"f": f"TSK-{tag}/1", "s": f"Tasca {tag}", "d": TODAY + timedelta(days=45)},
            )
        ).scalar_one()
        await session.execute(
            text("INSERT INTO contract_departments (contract_id, department_id) VALUES (:c, :d)"),
            {"c": contract, "d": dept},
        )
        outside = (
            await session.execute(
                text(
                    "INSERT INTO contracts (file_code, status, lot, subject) "
                    "VALUES (:f, 'Execució', '', :s) RETURNING id"
                ),
                {"f": f"TSK-{tag}/2", "s": f"Fora {tag}"},
            )
        ).scalar_one()
        await session.commit()
        data.update(dept=dept, contract=contract, outside=outside)

    yield data

    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "DELETE FROM tasks WHERE contract_id IN "
                "(SELECT id FROM contracts WHERE file_code LIKE :p)"
            ),
            {"p": f"TSK-{tag}%"},
        )
        await conn.execute(
            text("DELETE FROM contracts WHERE file_code LIKE :p"), {"p": f"TSK-{tag}%"}
        )
        await conn.execute(text("DELETE FROM departments WHERE code LIKE :p"), {"p": f"TK-{tag}"})
    await engine.dispose()


def _create(
    client: TestClient, headers: dict[str, str], world: dict[str, Any], **overrides: Any
) -> Any:
    payload = {
        "title": f"Revisió {world['tag']}",
        "task_type": "review",
        "due_date": str(TODAY + timedelta(days=10)),
        "contract_id": world["contract"],
        "assignee_ids": [world["employee"].id],
        "reminders": [{"offset_days": 7}, {"offset_days": 1, "channel": "webhook"}],
        **overrides,
    }
    return client.post("/api/v1/tasks", json=payload, headers=headers)


async def test_permissions_by_role(api_client: TestClient, world: dict[str, Any]) -> None:
    dm = login_headers(api_client, world["dm"].email)
    employee = login_headers(api_client, world["employee"].email)
    outsider = login_headers(api_client, world["employee_out"].email)

    # El responsable crea dins del seu àmbit.
    created = _create(api_client, dm, world)
    assert created.status_code == 201, created.text
    task = created.json()
    assert [a["id"] for a in task["assignees"]] == [world["employee"].id]
    assert len(task["reminders"]) == 2

    # employee no pot crear.
    denied = _create(api_client, employee, world)
    assert denied.status_code == 403

    # El responsable NO pot crear sobre un contracte fora del seu àmbit (404).
    out = _create(api_client, dm, world, contract_id=world["outside"])
    assert out.status_code == 404

    # L'assignat veu la tasca; el de fora no (404).
    assert api_client.get(f"/api/v1/tasks/{task['id']}", headers=employee).status_code == 200
    assert api_client.get(f"/api/v1/tasks/{task['id']}", headers=outsider).status_code == 404

    # L'assignat pot canviar l'estat però no editar.
    start = api_client.post(f"/api/v1/tasks/{task['id']}/actions/start", headers=employee)
    assert start.status_code == 200
    assert start.json()["status"] == "in_progress"
    edit = api_client.patch(
        f"/api/v1/tasks/{task['id']}", json={"title": "Canviat"}, headers=employee
    )
    assert edit.status_code == 403

    # El responsable edita, i el canvi queda a l'historial.
    edit = api_client.patch(f"/api/v1/tasks/{task['id']}", json={"priority": "high"}, headers=dm)
    assert edit.status_code == 200
    history = api_client.get(f"/api/v1/tasks/{task['id']}/history", headers=dm).json()["data"]
    assert any(e["field"] == "priority" and e["new_value"] == "high" for e in history)


async def test_complete_recurring_generates_next(
    api_client: TestClient, world: dict[str, Any]
) -> None:
    dm = login_headers(api_client, world["dm"].email)
    created = _create(
        api_client,
        dm,
        world,
        title=f"Informe trimestral {world['tag']}",
        task_type="report",
        recurrence="FREQ=MONTHLY;INTERVAL=3",
    )
    assert created.status_code == 201, created.text
    task = created.json()

    completed = api_client.post(
        f"/api/v1/tasks/{task['id']}/actions/complete",
        json={"resolution_notes": "Fet"},
        headers=dm,
    )
    assert completed.status_code == 200
    assert completed.json()["status"] == "done"
    assert completed.json()["resolution_notes"] == "Fet"

    # S'ha generat la següent ocurrència a +3 mesos amb assignats i recordatoris.
    listing = api_client.get(
        "/api/v1/tasks",
        params={"contract_id": world["contract"], "status": "pending"},
        headers=dm,
    ).json()["data"]
    follow_up = next((item for item in listing if item["parent_task_id"] == task["id"]), None)
    assert follow_up is not None
    assert follow_up["due_date"] > task["due_date"]
    assert [a["id"] for a in follow_up["assignees"]] == [world["employee"].id]
    assert len(follow_up["reminders"]) == 2

    # RRULE invàlida → 422.
    invalid = _create(api_client, dm, world, recurrence="CADA DIMARTS")
    assert invalid.status_code == 422


async def test_status_transitions_and_reopen(api_client: TestClient, world: dict[str, Any]) -> None:
    dm = login_headers(api_client, world["dm"].email)
    task = _create(api_client, dm, world).json()

    complete = api_client.post(f"/api/v1/tasks/{task['id']}/actions/complete", headers=dm)
    assert complete.status_code == 200
    # Completar dues vegades → 409.
    again = api_client.post(f"/api/v1/tasks/{task['id']}/actions/complete", headers=dm)
    assert again.status_code == 409

    reopened = api_client.post(f"/api/v1/tasks/{task['id']}/actions/reopen", headers=dm)
    assert reopened.status_code == 200
    assert reopened.json()["status"] == "pending"
    assert reopened.json()["completed_at"] is None


async def test_suggestions_from_alerts(api_client: TestClient, world: dict[str, Any]) -> None:
    dm = login_headers(api_client, world["dm"].email)

    suggestions = api_client.get("/api/v1/tasks/suggestions", headers=dm).json()["data"]
    mine = [s for s in suggestions if s["contract_id"] == world["contract"]]
    assert len(mine) == 1
    assert mine[0]["task_type"] == "extension"
    assert world["tag"] in mine[0]["file_code"] or mine[0]["file_code"].startswith("TSK")

    # Amb una tasca oberta del mateix tipus, el suggeriment desapareix.
    created = _create(api_client, dm, world, task_type="extension")
    assert created.status_code == 201
    suggestions = api_client.get("/api/v1/tasks/suggestions", headers=dm).json()["data"]
    assert not [s for s in suggestions if s["contract_id"] == world["contract"]]

    # L'employee de fora no veu el suggeriment del contracte aliè.
    outsider = login_headers(api_client, world["employee_out"].email)
    outsider_suggestions = api_client.get("/api/v1/tasks/suggestions", headers=outsider).json()[
        "data"
    ]
    assert not [s for s in outsider_suggestions if s["contract_id"] == world["contract"]]


async def test_suggestions_dedupe_sibling_lots(
    api_client: TestClient, world: dict[str, Any]
) -> None:
    dm = login_headers(api_client, world["dm"].email)
    tag = world["tag"]
    # Lot germà del mateix expedient, també amb alerta.
    async with session_factory() as session:
        sibling = (
            await session.execute(
                text(
                    "INSERT INTO contracts (file_code, status, lot, subject, "
                    "calculated_end_date, expiry_warning) "
                    "VALUES (:f, 'Execució', 'L2', :s, :d, true) RETURNING id"
                ),
                {
                    "f": f"TSK-{tag}/1",
                    "s": f"Lot germà {tag}",
                    "d": TODAY + timedelta(days=30),
                },
            )
        ).scalar_one()
        await session.execute(
            text("INSERT INTO contract_departments (contract_id, department_id) VALUES (:c, :d)"),
            {"c": sibling, "d": world["dept"]},
        )
        await session.commit()

    suggestions = api_client.get("/api/v1/tasks/suggestions", headers=dm).json()["data"]
    mine = [s for s in suggestions if s["file_code"] == f"TSK-{tag}/1"]
    assert len(mine) == 1  # un sol suggeriment per expedient
    # La data proposada és la més primerenca dels lots.
    assert mine[0]["due_date"] == str(TODAY + timedelta(days=30))


async def test_ical_feed_with_revocable_key(api_client: TestClient, world: dict[str, Any]) -> None:
    dm = login_headers(api_client, world["dm"].email)
    created = _create(api_client, dm, world, title=f"Tasca iCal {world['tag']}")
    assert created.status_code == 201

    # Sense clau vàlida: 401.
    bad = api_client.get("/api/v1/me/tasks.ics", params={"key": "x" * 32})
    assert bad.status_code == 401

    # L'assignat genera la clau i el feed conté la seva tasca.
    employee = login_headers(api_client, world["employee"].email)
    key = api_client.post("/api/v1/me/ical-key", headers=employee).json()["key"]
    feed = api_client.get("/api/v1/me/tasks.ics", params={"key": key})
    assert feed.status_code == 200
    assert feed.headers["content-type"].startswith("text/calendar")
    assert f"Tasca iCal {world['tag']}" in feed.text
    assert "BEGIN:VCALENDAR" in feed.text

    # Regenerar revoca la clau anterior.
    new_key = api_client.post("/api/v1/me/ical-key", headers=employee).json()["key"]
    assert new_key != key
    assert api_client.get("/api/v1/me/tasks.ics", params={"key": key}).status_code == 401
    assert api_client.get("/api/v1/me/tasks.ics", params={"key": new_key}).status_code == 200

    # Revocar del tot.
    assert api_client.delete("/api/v1/me/ical-key", headers=employee).status_code == 204
    assert api_client.get("/api/v1/me/tasks.ics", params={"key": new_key}).status_code == 401
