"""Processos BPM (specs/bpm.md): motor, permisos i mòdul activable."""

import uuid as uuid_module
from datetime import date, timedelta

import pytest
from sqlalchemy import text

from app.core.db import session_factory
from app.jobs.registry import JobContext
from app.modules.bpm.jobs import bpm_scan
from tests.conftest import login_headers

pytestmark = pytest.mark.anyio


async def _noop(_progress: int, _message: str | None = None) -> None:
    return None


def _scan_ctx() -> JobContext:
    return JobContext(job_id=uuid_module.uuid4(), payload=None, set_progress=_noop)


@pytest.fixture
async def bpm_world(make_user):  # type: ignore[no-untyped-def]
    tag = uuid_module.uuid4().hex[:8]
    admin = await make_user("admin")
    employee = await make_user("employee")

    async with session_factory() as session:
        dept = (
            await session.execute(
                text("INSERT INTO departments (code, name) VALUES (:c, 'BPM') RETURNING id"),
                {"c": f"BPM-{tag}"},
            )
        ).scalar_one()
        # Contracte ANTERIOR a qualsevol procés: mai ha de disparar res.
        old_contract = (
            await session.execute(
                text(
                    "INSERT INTO contracts (file_code, status, lot, subject, published_at, "
                    "created_at) VALUES (:f, 'Formalitzat', '', :s, '2026-01-01', "
                    "now() - interval '30 days') RETURNING id"
                ),
                {"f": f"BPM-{tag}/OLD", "s": f"Antic {tag}"},
            )
        ).scalar_one()
        await session.commit()

    yield {
        "tag": tag,
        "admin": admin,
        "employee": employee,
        "dept": dept,
        "old_contract": old_contract,
    }

    async with session_factory() as session:
        await session.execute(
            text("DELETE FROM bpm_workflows WHERE name LIKE :p"), {"p": f"Proc {tag}%"}
        )
        await session.execute(
            text("DELETE FROM contracts WHERE file_code LIKE :p"), {"p": f"BPM-{tag}%"}
        )
        await session.execute(text("DELETE FROM departments WHERE code = :c"), {"c": f"BPM-{tag}"})
        await session.commit()


def _workflow_body(w, **overrides):  # type: ignore[no-untyped-def]
    body = {
        "name": f"Proc {w['tag']} supervisió",
        "trigger": "contract_created",
        "active": True,
        "steps": [
            {
                "title": f"Primer pas {w['tag']}",
                "task_type": "review",
                "offset_days": 0,
                "assignee_kind": "user",
                "assignee_user_id": w["employee"].id,
            },
            {
                "title": f"Segon pas {w['tag']}",
                "task_type": "report",
                "offset_days": 10,
                "assignee_kind": "department",
                "assignee_department_id": w["dept"],
            },
        ],
    }
    body.update(overrides)
    return body


async def test_full_sequence_lifecycle(api_client, bpm_world) -> None:  # type: ignore[no-untyped-def]
    w = bpm_world
    admin = login_headers(api_client, w["admin"].email)

    created = api_client.post("/api/v1/bpm/workflows", json=_workflow_body(w), headers=admin)
    assert created.status_code == 201, created.text
    workflow_id = created.json()["id"]
    assert [s["position"] for s in created.json()["steps"]] == [1, 2]

    # Contracte creat DESPRÉS del procés: l'escaneig obre la instància.
    async with session_factory() as session:
        contract = (
            await session.execute(
                text(
                    "INSERT INTO contracts (file_code, status, lot, subject, published_at) "
                    "VALUES (:f, 'Anunci en licitació', '', :s, '2026-02-01') RETURNING id"
                ),
                {"f": f"BPM-{w['tag']}/NEW", "s": f"Nou {w['tag']}"},
            )
        ).scalar_one()
        await session.commit()

    result = await bpm_scan(_scan_ctx())
    assert result["started"] >= 1

    instances = api_client.get(
        "/api/v1/bpm/instances", params={"workflow_id": workflow_id}, headers=admin
    ).json()["data"]
    mine = [i for i in instances if i["contract_id"] == contract]
    assert len(mine) == 1, "una instància per al contracte nou"
    assert all(i["contract_id"] != w["old_contract"] for i in instances), (
        "el contracte anterior al procés no dispara res"
    )
    instance = mine[0]
    assert instance["status"] == "running" and instance["current_position"] == 1

    # La primera tasca és de l'assignat i el segon escaneig no la duplica.
    employee = login_headers(api_client, w["employee"].email)
    tasks = api_client.get(
        "/api/v1/tasks", params={"contract_id": contract}, headers=employee
    ).json()["data"]
    first = next(t for t in tasks if t["title"].startswith("Primer pas"))
    assert [a["id"] for a in first["assignees"]] == [w["employee"].id]
    await bpm_scan(_scan_ctx())
    tasks = api_client.get(
        "/api/v1/tasks", params={"contract_id": contract}, headers=employee
    ).json()["data"]
    assert len([t for t in tasks if t["title"].startswith("Primer pas")]) == 1

    # Completar el primer pas → el segon apareix amb el desfasament de dies.
    done = api_client.post(
        f"/api/v1/tasks/{first['id']}/actions/complete", json={}, headers=employee
    )
    assert done.status_code == 200, done.text
    await bpm_scan(_scan_ctx())

    admin_tasks = api_client.get(
        "/api/v1/tasks", params={"contract_id": contract}, headers=admin
    ).json()["data"]
    second = next(t for t in admin_tasks if t["title"].startswith("Segon pas"))
    assert second["department_id"] == w["dept"]
    assert second["due_date"] == (date.today() + timedelta(days=10)).isoformat()

    # Completar l'últim pas tanca la instància.
    finish = api_client.post(
        f"/api/v1/tasks/{second['id']}/actions/complete", json={}, headers=admin
    )
    assert finish.status_code == 200, finish.text
    await bpm_scan(_scan_ctx())
    refreshed = api_client.get(
        "/api/v1/bpm/instances", params={"workflow_id": workflow_id}, headers=admin
    ).json()["data"]
    assert next(i for i in refreshed if i["id"] == instance["id"])["status"] == "done"


async def test_deleting_current_task_cancels_instance(api_client, bpm_world) -> None:  # type: ignore[no-untyped-def]
    w = bpm_world
    admin = login_headers(api_client, w["admin"].email)
    body = _workflow_body(w, name=f"Proc {w['tag']} cancel", trigger="manual")
    workflow_id = api_client.post("/api/v1/bpm/workflows", json=body, headers=admin).json()["id"]

    async with session_factory() as session:
        contract = (
            await session.execute(
                text(
                    "INSERT INTO contracts (file_code, status, lot, subject, published_at) "
                    "VALUES (:f, 'Adjudicat', '', :s, '2026-02-01') RETURNING id"
                ),
                {"f": f"BPM-{w['tag']}/MAN", "s": f"Manual {w['tag']}"},
            )
        ).scalar_one()
        await session.commit()

    started = api_client.post(
        f"/api/v1/bpm/workflows/{workflow_id}/actions/start",
        params={"contract_id": contract},
        headers=admin,
    )
    assert started.status_code == 201, started.text
    instance = started.json()
    # Arrencar dos cops → 409.
    assert (
        api_client.post(
            f"/api/v1/bpm/workflows/{workflow_id}/actions/start",
            params={"contract_id": contract},
            headers=admin,
        ).status_code
        == 409
    )

    deleted = api_client.delete(f"/api/v1/tasks/{instance['current_task_id']}", headers=admin)
    assert deleted.status_code == 204
    await bpm_scan(_scan_ctx())
    refreshed = api_client.get(
        "/api/v1/bpm/instances", params={"contract_id": contract}, headers=admin
    ).json()["data"]
    assert refreshed[0]["status"] == "cancelled"


async def test_permissions_and_module_flag(api_client, bpm_world, make_user) -> None:  # type: ignore[no-untyped-def]
    w = bpm_world
    employee = login_headers(api_client, w["employee"].email)
    assert api_client.get("/api/v1/bpm/workflows", headers=employee).status_code == 403

    manager = await make_user("procurement_manager")
    pm = login_headers(api_client, manager.email)
    assert api_client.get("/api/v1/bpm/workflows", headers=pm).status_code == 200

    # Mòdul desactivat: 403 module-disabled per a tothom i escaneig aturat.
    from sqlalchemy import select

    from app.core import modules as module_flags
    from app.modules.config.models import Setting

    async with session_factory() as session:
        setting = (
            await session.execute(select(Setting).where(Setting.key == module_flags.SETTING_KEY))
        ).scalar_one_or_none()
        previous = setting.value if setting is not None else None
        if setting is None:
            session.add(Setting(key=module_flags.SETTING_KEY, value=["bpm"]))
        else:
            setting.value = ["bpm"]
        await session.commit()
    module_flags.invalidate_cache()
    try:
        admin = login_headers(api_client, w["admin"].email)
        blocked = api_client.get("/api/v1/bpm/workflows", headers=admin)
        assert blocked.status_code == 403
        assert blocked.json()["type"].endswith("module-disabled")
        assert (await bpm_scan(_scan_ctx())) == {"skipped": "module-disabled"}
    finally:
        async with session_factory() as session:
            setting = (
                await session.execute(
                    select(Setting).where(Setting.key == module_flags.SETTING_KEY)
                )
            ).scalar_one()
            setting.value = previous if previous is not None else []
            await session.commit()
        module_flags.invalidate_cache()
