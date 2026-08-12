"""Accions de contracte, assignació massiva i alerts.recompute."""

import json
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
from app.integrations import hub
from app.jobs.registry import JobContext
from app.modules.contracts.alerts import recompute_alerts

TODAY = date.today()


async def _run_recompute() -> dict[str, Any]:
    async def _noop(_pct: int, _msg: str | None = None) -> None:
        return None

    result = await recompute_alerts(JobContext(job_id=uuid4(), payload=None, set_progress=_noop))
    assert result is not None
    return result


@pytest.fixture
async def world(make_user) -> AsyncIterator[dict[str, Any]]:  # type: ignore[no-untyped-def]
    """Departament A; dm_manager és responsable del contracte, dm_plain no."""
    tag = uuid4().hex[:8]
    data: dict[str, Any] = {"tag": tag}

    data["admin"] = await make_user("admin")
    data["pm"] = await make_user("procurement_manager")
    data["dm_manager"] = await make_user("dept_manager")
    data["dm_plain"] = await make_user("dept_manager")
    data["employee"] = await make_user("employee")

    async with session_factory() as session:
        dept = (
            await session.execute(
                text("INSERT INTO departments (code, name) VALUES (:c, 'ACC') RETURNING id"),
                {"c": f"AC-{tag}"},
            )
        ).scalar_one()
        dept_other = (
            await session.execute(
                text("INSERT INTO departments (code, name) VALUES (:c, 'ACC2') RETURNING id"),
                {"c": f"AD-{tag}"},
            )
        ).scalar_one()
        for user in (data["dm_manager"], data["dm_plain"], data["employee"]):
            await session.execute(
                text("INSERT INTO user_departments (user_id, department_id) VALUES (:u, :d)"),
                {"u": user.id, "d": dept},
            )

        main_id = (
            await session.execute(
                text(
                    "INSERT INTO contracts (file_code, status, lot, subject, "
                    "calculated_end_date, possibly_finished) "
                    "VALUES (:f, 'Execució', '', :s, :d, true) RETURNING id"
                ),
                {"f": f"ACT-{tag}/1", "s": f"Acció {tag}", "d": TODAY - timedelta(days=30)},
            )
        ).scalar_one()
        await session.execute(
            text("INSERT INTO contract_departments (contract_id, department_id) VALUES (:c, :d)"),
            {"c": main_id, "d": dept},
        )
        await session.execute(
            text("INSERT INTO contract_managers (contract_id, user_id) VALUES (:c, :u)"),
            {"c": main_id, "u": data["dm_manager"].id},
        )
        bulk_ids = []
        for suffix in ("2", "3"):
            bulk_ids.append(
                (
                    await session.execute(
                        text(
                            "INSERT INTO contracts (file_code, status, lot, subject) "
                            "VALUES (:f, 'Execució', '', :s) RETURNING id"
                        ),
                        {"f": f"ACT-{tag}/{suffix}", "s": f"Acció {tag}"},
                    )
                ).scalar_one()
            )
        bulk_a, bulk_b = bulk_ids
        await session.commit()
        data.update(dept=dept, dept_other=dept_other, main=main_id, bulk_a=bulk_a, bulk_b=bulk_b)

    yield data

    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.execute(
            text("DELETE FROM contracts WHERE file_code LIKE :p"), {"p": f"ACT-{tag}%"}
        )
        await conn.execute(text("DELETE FROM departments WHERE code LIKE :p"), {"p": f"A_-{tag}"})
    await engine.dispose()


def _headers(client: TestClient, email: str) -> dict[str, str]:
    from tests.conftest import login_headers

    return login_headers(client, email)


# ─────────────────────────── finish / dismiss ───────────────────────────


async def test_finish_requires_being_contract_manager(
    api_client: TestClient, world: dict[str, Any]
) -> None:
    url = f"/api/v1/contracts/{world['main']}/actions/finish"

    # dept_manager del departament però NO responsable del contracte: 403.
    denied = api_client.post(url, headers=_headers(api_client, world["dm_plain"].email))
    assert denied.status_code == 403

    # employee: mai.
    denied = api_client.post(url, headers=_headers(api_client, world["employee"].email))
    assert denied.status_code == 403

    # responsable del contracte: sí.
    response = api_client.post(url, headers=_headers(api_client, world["dm_manager"].email))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "Finalitzat"
    assert body["possibly_finished"] is False

    # Ja finalitzat: 409.
    again = api_client.post(url, headers=_headers(api_client, world["admin"].email))
    assert again.status_code == 409

    # Historial amb el canvi d'estat.
    history = api_client.get(
        f"/api/v1/contracts/{world['main']}/history",
        headers=_headers(api_client, world["admin"].email),
    )
    fields = [e["field"] for e in history.json()["data"]]
    assert "status" in fields


async def test_dismiss_expiry_is_persistent_until_end_date_changes(
    api_client: TestClient, world: dict[str, Any]
) -> None:
    contract_id = world["main"]
    url = f"/api/v1/contracts/{contract_id}/actions/dismiss-expiry"
    headers = _headers(api_client, world["admin"].email)

    response = api_client.post(url, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["possibly_finished"] is False

    # Sense alerta activa: 409.
    assert api_client.post(url, headers=headers).status_code == 409

    # recompute NO torna a aixecar l'alerta (descart vigent).
    await _run_recompute()
    detail = api_client.get(f"/api/v1/contracts/{contract_id}", headers=headers).json()
    assert detail["possibly_finished"] is False

    # Si la data final canvia, el descart caduca i l'alerta torna.
    async with session_factory() as session:
        await session.execute(
            text("UPDATE contracts SET calculated_end_date = :d WHERE id = :id"),
            {"d": TODAY - timedelta(days=5), "id": contract_id},
        )
        await session.commit()
    await _run_recompute()
    detail = api_client.get(f"/api/v1/contracts/{contract_id}", headers=headers).json()
    assert detail["possibly_finished"] is True


# ─────────────────────────── alerts.recompute ───────────────────────────


async def test_recompute_alert_rules(world: dict[str, Any]) -> None:
    tag = world["tag"]
    cases = {
        f"ALR-{tag}/past": (TODAY - timedelta(days=10), "Execució"),
        f"ALR-{tag}/soon": (TODAY + timedelta(days=60), "Execució"),
        f"ALR-{tag}/far": (TODAY + timedelta(days=400), "Execució"),
        f"ALR-{tag}/dead": (TODAY - timedelta(days=10), "Desert"),
    }
    async with session_factory() as session:
        for file_code, (end, status) in cases.items():
            await session.execute(
                text(
                    "INSERT INTO contracts (file_code, status, lot, subject, calculated_end_date)"
                    " VALUES (:f, :st, '', 'Alerta', :d)"
                ),
                {"f": file_code, "st": status, "d": end},
            )
        await session.commit()

    summary = await _run_recompute()
    assert summary["window_months"] == 6

    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    async with engine.connect() as conn:
        rows = {
            r.file_code: r
            for r in (
                await conn.execute(
                    text(
                        "SELECT file_code, expiry_warning, possibly_finished FROM contracts "
                        "WHERE file_code LIKE :p"
                    ),
                    {"p": f"ALR-{tag}%"},
                )
            ).all()
        }
    async with engine.begin() as conn:
        await conn.execute(
            text("DELETE FROM contracts WHERE file_code LIKE :p"), {"p": f"ALR-{tag}%"}
        )
    await engine.dispose()

    assert rows[f"ALR-{tag}/past"].possibly_finished is True
    assert rows[f"ALR-{tag}/past"].expiry_warning is False
    assert rows[f"ALR-{tag}/soon"].expiry_warning is True
    assert rows[f"ALR-{tag}/soon"].possibly_finished is False
    assert rows[f"ALR-{tag}/far"].expiry_warning is False
    assert rows[f"ALR-{tag}/dead"].possibly_finished is False  # estat mort


# ─────────────────────────── enrich ───────────────────────────


async def test_enrich_action_queues_job(api_client: TestClient, world: dict[str, Any]) -> None:
    contract_id = world["bulk_a"]
    async with session_factory() as session:
        await session.execute(
            text("UPDATE contracts SET phase_urls = :u WHERE id = :id"),
            {
                "u": json.dumps({"licitacio": "https://contractaciopublica.cat/x"}),
                "id": contract_id,
            },
        )
        record = (
            await session.execute(text("SELECT enabled FROM connectors WHERE slug = 'pscp'"))
        ).scalar_one_or_none()
        pscp = await hub.ensure_registered(session, "pscp")
        pscp.enabled = True
        await session.commit()

    url = f"/api/v1/contracts/{contract_id}/actions/enrich"

    # employee: 403.
    assert (
        api_client.post(url, headers=_headers(api_client, world["employee"].email)).status_code
        == 403
    )

    response = api_client.post(url, headers=_headers(api_client, world["admin"].email))
    assert response.status_code == 202, response.text
    job = response.json()
    assert job["type"] == "enrich.contract"

    # Connector desactivat: 409.
    async with session_factory() as session:
        await session.execute(text("UPDATE connectors SET enabled = false WHERE slug = 'pscp'"))
        await session.commit()
    denied = api_client.post(
        f"/api/v1/contracts/{world['bulk_b']}/actions/enrich",
        headers=_headers(api_client, world["admin"].email),
    )
    assert denied.status_code in (409, 422)  # 409 connector-disabled (o sense phase_urls)

    async with session_factory() as session:
        await session.execute(
            text("UPDATE connectors SET enabled = :e WHERE slug = 'pscp'"),
            {"e": bool(record)},
        )
        await session.execute(text("DELETE FROM jobs WHERE id = :id"), {"id": job["id"]})
        await session.commit()


# ─────────────────────────── bulk assign ───────────────────────────


async def test_bulk_assign_add_replace_and_errors(
    api_client: TestClient, world: dict[str, Any]
) -> None:
    admin = _headers(api_client, world["admin"].email)
    url = "/api/v1/contracts/bulk/assign-departments"

    # employee: 403.
    denied = api_client.post(
        url,
        json={"contract_ids": [world["bulk_a"]], "department_ids": [world["dept"]]},
        headers=_headers(api_client, world["employee"].email),
    )
    assert denied.status_code == 403

    # Departament inexistent: 422.
    invalid = api_client.post(
        url,
        json={"contract_ids": [world["bulk_a"]], "department_ids": [99999999]},
        headers=admin,
    )
    assert invalid.status_code == 422

    # add: assigna i reporta els ids inexistents.
    response = api_client.post(
        url,
        json={
            "contract_ids": [world["bulk_a"], world["bulk_b"], 99999999],
            "department_ids": [world["dept"]],
            "mode": "add",
        },
        headers=admin,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["updated"] == 2
    assert body["missing"] == [99999999]

    # add idempotent: sense canvis.
    repeat = api_client.post(
        url,
        json={
            "contract_ids": [world["bulk_a"]],
            "department_ids": [world["dept"]],
            "mode": "add",
        },
        headers=admin,
    )
    assert repeat.json()["updated"] == 0

    # replace: substitueix el conjunt sencer.
    replaced = api_client.post(
        url,
        json={
            "contract_ids": [world["bulk_a"]],
            "department_ids": [world["dept_other"]],
            "mode": "replace",
        },
        headers=admin,
    )
    assert replaced.json()["updated"] == 1
    async with session_factory() as session:
        departments = (
            await session.execute(
                text("SELECT department_id FROM contract_departments WHERE contract_id = :c"),
                {"c": world["bulk_a"]},
            )
        ).scalars()
        assert list(departments) == [world["dept_other"]]
