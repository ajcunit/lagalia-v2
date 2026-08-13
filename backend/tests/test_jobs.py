"""Integració de la cua de treballs: runner, accés, token efímer, SSE."""

import json
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

import app.jobs.tasks  # noqa: F401 — registra system.heartbeat
from app.core.config import settings
from app.core.problems import Problem
from app.jobs import events, runner, service
from app.jobs.registry import JobContext, job
from app.jobs.scheduler import SCHEDULER_LOCK_KEY
from tests.conftest import MakeUser, TestUser, login_headers


@job("test.fail")
async def _failing_handler(_ctx: JobContext) -> dict[str, Any]:
    raise ValueError("m'he trencat expressament")


_created_job_ids: list[uuid.UUID] = []


@pytest.fixture(autouse=True)
async def _cleanup_jobs() -> Any:
    yield
    if not _created_job_ids:
        return
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.execute(
            text("DELETE FROM jobs WHERE id = ANY(:ids)"), {"ids": list(_created_job_ids)}
        )
    await engine.dispose()
    _created_job_ids.clear()


async def _insert_job(
    *, job_type: str = "system.heartbeat", created_by: int, status: str = "queued"
) -> uuid.UUID:
    job_id = uuid.uuid4()
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO jobs (id, type, status, created_by) "
                "VALUES (:id, :type, :status, :created_by)"
            ),
            {"id": job_id, "type": job_type, "status": status, "created_by": created_by},
        )
    await engine.dispose()
    _created_job_ids.append(job_id)
    return job_id


async def _job_row(job_id: uuid.UUID) -> dict[str, Any]:
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    async with engine.connect() as conn:
        row = (
            (
                await conn.execute(
                    text(
                        "SELECT status, progress, progress_message, result, error, attempts, "
                        "started_at, finished_at FROM jobs WHERE id = :id"
                    ),
                    {"id": job_id},
                )
            )
            .mappings()
            .one()
        )
    await engine.dispose()
    return dict(row)


async def test_runner_success_transitions(make_user: MakeUser) -> None:
    user: TestUser = await make_user("employee")
    job_id = await _insert_job(created_by=user.id)

    await runner.execute_job(str(job_id))

    row = await _job_row(job_id)
    assert row["status"] == "success"
    assert row["progress"] == 100
    assert json.loads(json.dumps(row["result"]))["beat_at"]
    assert row["attempts"] == 1
    assert row["started_at"] is not None
    assert row["finished_at"] is not None


async def test_runner_failure_records_error(make_user: MakeUser) -> None:
    user: TestUser = await make_user("employee")
    job_id = await _insert_job(job_type="test.fail", created_by=user.id)

    await runner.execute_job(str(job_id))

    row = await _job_row(job_id)
    assert row["status"] == "failed"
    assert "ValueError" in row["error"]
    assert "expressament" in row["error"]


async def test_runner_skips_cancelled_job(make_user: MakeUser) -> None:
    user: TestUser = await make_user("employee")
    job_id = await _insert_job(created_by=user.id, status="cancelled")

    await runner.execute_job(str(job_id))

    row = await _job_row(job_id)
    assert row["status"] == "cancelled"
    assert row["attempts"] == 0


async def test_dedup_key_blocks_second_live_job(make_user: MakeUser) -> None:
    from app.core.db import session_factory

    user: TestUser = await make_user("employee")
    dedup = f"test-dedup-{uuid.uuid4().hex[:8]}"

    async with session_factory() as session:
        first = await service.enqueue_job(
            session, job_type="system.heartbeat", created_by=user.id, dedup_key=dedup
        )
    _created_job_ids.append(first.id)
    assert first.status.value == "queued"

    async with session_factory() as session:
        with pytest.raises(Problem) as excinfo:
            await service.enqueue_job(
                session, job_type="system.heartbeat", created_by=user.id, dedup_key=dedup
            )
    assert excinfo.value.status_code == 409


async def test_job_access_rules(api_client: TestClient, make_user: MakeUser) -> None:
    creator: TestUser = await make_user("employee")
    other: TestUser = await make_user("employee")
    admin: TestUser = await make_user("admin")
    job_id = await _insert_job(created_by=creator.id)

    as_creator = api_client.get(
        f"/api/v1/jobs/{job_id}", headers=login_headers(api_client, creator.email)
    )
    as_other = api_client.get(
        f"/api/v1/jobs/{job_id}", headers=login_headers(api_client, other.email)
    )
    as_admin = api_client.get(
        f"/api/v1/jobs/{job_id}", headers=login_headers(api_client, admin.email)
    )

    assert as_creator.status_code == 200
    assert as_creator.json()["type"] == "system.heartbeat"
    assert "payload" not in as_creator.json()
    assert as_other.status_code == 403
    assert as_admin.status_code == 200


async def test_cancel_queued_job(api_client: TestClient, make_user: MakeUser) -> None:
    creator: TestUser = await make_user("employee")
    job_id = await _insert_job(created_by=creator.id)
    headers = login_headers(api_client, creator.email)

    cancelled = api_client.post(f"/api/v1/jobs/{job_id}/actions/cancel", headers=headers)
    assert cancelled.status_code == 202
    assert cancelled.json()["status"] == "cancelled"

    again = api_client.post(f"/api/v1/jobs/{job_id}/actions/cancel", headers=headers)
    assert again.status_code == 409


async def test_ephemeral_token_is_single_use_and_scoped(
    api_client: TestClient, make_user: MakeUser
) -> None:
    creator: TestUser = await make_user("employee")
    job_id = await _insert_job(created_by=creator.id, status="success")
    other_job = await _insert_job(created_by=creator.id, status="success")
    headers = login_headers(api_client, creator.email)

    issued = api_client.post(
        "/api/v1/auth/ephemeral",
        json={"purpose": "job_events", "resource": str(job_id)},
        headers=headers,
    )
    assert issued.status_code == 201
    token = issued.json()["token"]

    # Recurs equivocat → 401 (i el token queda consumit: un sol ús).
    wrong = api_client.get(f"/api/v1/jobs/{other_job}/events", params={"token": token})
    assert wrong.status_code == 401

    reused = api_client.get(f"/api/v1/jobs/{job_id}/events", params={"token": token})
    assert reused.status_code == 401


async def test_ephemeral_denied_for_foreign_job(
    api_client: TestClient, make_user: MakeUser
) -> None:
    creator: TestUser = await make_user("employee")
    other: TestUser = await make_user("employee")
    job_id = await _insert_job(created_by=creator.id)

    response = api_client.post(
        "/api/v1/auth/ephemeral",
        json={"purpose": "job_events", "resource": str(job_id)},
        headers=login_headers(api_client, other.email),
    )

    assert response.status_code == 403


async def test_sse_generator_relays_pubsub_events(make_user: MakeUser) -> None:
    """Camí pub/sub, directament sobre el generador (subscripció controlada)."""
    import asyncio

    from app.jobs.router import _event_stream

    user: TestUser = await make_user("employee")
    job_id = await _insert_job(created_by=user.id, status="running")

    stream = _event_stream(job_id, {"id": str(job_id), "status": "running", "progress": 0})
    first = await anext(stream)
    assert '"status": "running"' in first

    # El generador se subscriu en reprendre's: li donem marge abans de publicar.
    next_event = asyncio.ensure_future(anext(stream))
    await asyncio.sleep(0.5)
    await events.publish_event(job_id, {"id": str(job_id), "status": "success", "progress": 100})
    second = await asyncio.wait_for(next_event, timeout=10)
    assert '"status": "success"' in second

    with pytest.raises(StopAsyncIteration):
        await asyncio.wait_for(anext(stream), timeout=10)


async def test_sse_generator_recovers_lost_terminal_event(
    make_user: MakeUser, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Si el missatge terminal es perd, la revalidació a BD tanca l'stream."""
    import asyncio

    from app.jobs import router as jobs_router
    from app.jobs.router import _event_stream

    monkeypatch.setattr(jobs_router, "_HEARTBEAT_SECONDS", 1)

    user: TestUser = await make_user("employee")
    job_id = await _insert_job(created_by=user.id, status="running")

    stream = _event_stream(job_id, {"id": str(job_id), "status": "running", "progress": 0})
    first = await anext(stream)
    assert '"status": "running"' in first

    # El job acaba "per fora" sense publicar res al pub/sub (missatge perdut).
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.execute(
            text("UPDATE jobs SET status = 'success', progress = 100 WHERE id = :id"),
            {"id": job_id},
        )
    await engine.dispose()

    second = await asyncio.wait_for(anext(stream), timeout=10)
    assert '"status": "success"' in second

    with pytest.raises(StopAsyncIteration):
        await asyncio.wait_for(anext(stream), timeout=10)


async def test_sse_terminal_job_closes_immediately(
    api_client: TestClient, make_user: MakeUser
) -> None:
    creator: TestUser = await make_user("employee")
    job_id = await _insert_job(created_by=creator.id, status="success")
    headers = login_headers(api_client, creator.email)
    token = api_client.post(
        "/api/v1/auth/ephemeral",
        json={"purpose": "job_events", "resource": str(job_id)},
        headers=headers,
    ).json()["token"]

    response = api_client.get(f"/api/v1/jobs/{job_id}/events", params={"token": token})

    assert response.status_code == 200
    assert '"status": "success"' in response.text


async def test_scheduler_lock_is_exclusive() -> None:
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    async with engine.connect() as first, engine.connect() as second:
        got_first = (
            await first.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": SCHEDULER_LOCK_KEY})
        ).scalar_one()
        if got_first is False:
            # Un scheduler VIU (dev) manté el lock: precisament el comportament
            # que aquest test garanteix. Es verifica l'exclusió i prou.
            pytest.skip("el scheduler de desenvolupament manté el lock (exclusió activa)")
        got_second = (
            await second.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": SCHEDULER_LOCK_KEY})
        ).scalar_one()

        assert got_first is True
        assert got_second is False

        await first.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": SCHEDULER_LOCK_KEY})
    await engine.dispose()
