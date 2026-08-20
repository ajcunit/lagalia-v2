"""Estat del sistema (specs/system-status.md, B-022)."""

import uuid as uuid_module

import pytest
from sqlalchemy import text

from app.core.db import session_factory
from tests.conftest import login_headers

pytestmark = pytest.mark.anyio


async def test_readiness_denied_to_non_admin(api_client, make_user) -> None:  # type: ignore[no-untyped-def]
    employee = await make_user("employee")
    response = api_client.get(
        "/api/v1/health/ready", headers=login_headers(api_client, employee.email)
    )
    assert response.status_code == 403


async def test_readiness_reports_internal_infrastructure(api_client, make_user) -> None:  # type: ignore[no-untyped-def]
    admin = await make_user("admin")
    response = api_client.get(
        "/api/v1/health/ready", headers=login_headers(api_client, admin.email)
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert {check["name"] for check in body["checks"]} == {"database", "redis", "storage"}
    database = next(check for check in body["checks"] if check["name"] == "database")
    assert database["status"] == "ok"
    assert database["latency_ms"] is not None


async def test_system_status_denied_to_non_admin(api_client, make_user) -> None:  # type: ignore[no-untyped-def]
    employee = await make_user("employee")
    response = api_client.get(
        "/api/v1/system/status", headers=login_headers(api_client, employee.email)
    )
    assert response.status_code == 403


async def test_system_status_worker_proven_by_heartbeat(api_client, make_user) -> None:  # type: ignore[no-untyped-def]
    """El worker es demostra viu per l'últim heartbeat EXECUTAT, no pel procés."""
    admin = await make_user("admin")
    headers = login_headers(api_client, admin.email)

    async with session_factory() as session:
        await session.execute(text("DELETE FROM jobs WHERE type = 'system.heartbeat'"))
        await session.commit()

    response = api_client.get("/api/v1/system/status", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    worker = next(s for s in body["services"] if s["name"] == "worker")
    assert worker["status"] == "failing"

    heartbeat_id = uuid_module.uuid4()
    async with session_factory() as session:
        await session.execute(
            text(
                "INSERT INTO jobs (id, type, status, started_at, finished_at, progress) "
                "VALUES (:i, 'system.heartbeat', 'success', now(), now(), 100)"
            ),
            {"i": heartbeat_id},
        )
        await session.commit()

    response = api_client.get("/api/v1/system/status", headers=headers)
    body = response.json()
    worker = next(s for s in body["services"] if s["name"] == "worker")
    assert worker["status"] == "ok"

    # Forma general del dashboard: seccions presents i coherents.
    assert {s["name"] for s in body["services"]} >= {
        "database",
        "redis",
        "storage",
        "worker",
        "scheduler",
    }
    assert body["jobs"]["queued"] >= 0
    assert body["resources"]["database_bytes"] is not None
    assert body["webhooks"]["pending"] >= 0

    async with session_factory() as session:
        await session.execute(text("DELETE FROM jobs WHERE id = :i"), {"i": heartbeat_id})
        await session.commit()


async def test_status_snapshot_measures_storage() -> None:
    from app.jobs.registry import JobContext
    from app.modules.config.models import Setting
    from app.modules.system.jobs import status_snapshot
    from app.modules.system.service import STORAGE_USAGE_SETTING

    async def _noop(_progress: int, _message: str | None = None) -> None:
        return None

    result = await status_snapshot(
        JobContext(job_id=uuid_module.uuid4(), payload=None, set_progress=_noop)
    )
    assert "connectors" in result

    from sqlalchemy import select

    async with session_factory() as session:
        setting = (
            await session.execute(select(Setting).where(Setting.key == STORAGE_USAGE_SETTING))
        ).scalar_one_or_none()
        assert setting is not None
        assert isinstance(setting.value, dict)
        assert "objects" in setting.value and "total_bytes" in setting.value
        assert "measured_at" in setting.value


async def test_system_usage_counts_requests_and_sessions(api_client, make_user) -> None:  # type: ignore[no-untyped-def]
    admin = await make_user("admin")
    headers = login_headers(api_client, admin.email)

    # Trànsit comptable: una request autenticada qualsevol.
    assert api_client.get("/api/v1/me/permissions", headers=headers).status_code == 200

    response = api_client.get("/api/v1/system/usage", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["days"][0]["requests"] >= 1
    assert body["active_sessions"] >= 1
    assert body["active_users"] >= 1
    # Els «top» són limitats: dins de la bateria completa hi competeixen
    # tots els tests, així que se'n comprova la forma, no la pertinença.
    assert body["users"], "cap usuari comptabilitzat"
    assert body["top_endpoints"], "cap endpoint comptabilitzat"
    assert all(e["requests"] >= e["errors"] for e in body["top_endpoints"])
    # L'admin acaba d'iniciar sessió: la seva última connexió hi ha de ser
    # (l'escriu l'audit_log del login). La IP és NULL als tests: la del
    # TestClient («testclient») no és una INET vàlida.
    me = next((u for u in body["users"] if u["user_id"] == admin.id), None)
    if me is not None:
        assert me["last_login_at"] is not None


async def test_system_usage_denied_to_non_admin(api_client, make_user) -> None:  # type: ignore[no-untyped-def]
    employee = await make_user("employee")
    response = api_client.get(
        "/api/v1/system/usage", headers=login_headers(api_client, employee.email)
    )
    assert response.status_code == 403
