"""Reintents amb backoff, DLQ i escombrat (specs/jobs-queue.md, B-009)."""

import uuid as uuid_module

import pytest
from sqlalchemy import text

from app.core.db import session_factory
from app.jobs import runner
from app.jobs.models import Job, JobStatus
from app.jobs.registry import JobContext, get_policy, job
from tests.conftest import login_headers

pytestmark = pytest.mark.anyio

_CALLS: dict[str, int] = {}


def _register_flaky(max_attempts: int, fail_times: int) -> str:
    """Registra un tipus de job únic que falla les primeres N execucions."""
    name = f"test.flaky_{uuid_module.uuid4().hex[:8]}"

    @job(name, max_attempts=max_attempts, backoff_seconds=1)
    async def flaky(ctx: JobContext) -> dict:  # type: ignore[no-untyped-def]
        _CALLS[name] = _CALLS.get(name, 0) + 1
        if _CALLS[name] <= fail_times:
            raise RuntimeError(f"fallada simulada {_CALLS[name]}")
        return {"ok": True}

    return name


async def _insert_job(job_type: str) -> Job:
    async with session_factory() as session:
        row = Job(type=job_type)
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row


async def test_retry_then_success() -> None:
    job_type = _register_flaky(max_attempts=3, fail_times=1)
    assert get_policy(job_type).max_attempts == 3
    row = await _insert_job(job_type)

    # Primera execució: falla → torna a la cua amb reintent programat.
    await runner.execute_job(str(row.id))
    async with session_factory() as session:
        refreshed = await session.get(Job, row.id)
        assert refreshed.status == JobStatus.QUEUED
        assert refreshed.attempts == 1
        assert "reintent 2/3" in (refreshed.progress_message or "")
        assert "fallada simulada" in (refreshed.error or "")

    # Segona execució (l'arq diferit la faria): èxit.
    await runner.execute_job(str(row.id))
    async with session_factory() as session:
        refreshed = await session.get(Job, row.id)
        assert refreshed.status == JobStatus.SUCCESS
        assert refreshed.attempts == 2
        await session.execute(text("DELETE FROM jobs WHERE id = :i"), {"i": row.id})
        await session.commit()


async def test_exhausted_retries_go_dead() -> None:
    job_type = _register_flaky(max_attempts=2, fail_times=99)
    row = await _insert_job(job_type)

    await runner.execute_job(str(row.id))  # 1a: reintent programat
    await runner.execute_job(str(row.id))  # 2a: esgotat → dead
    async with session_factory() as session:
        refreshed = await session.get(Job, row.id)
        assert refreshed.status == JobStatus.DEAD
        assert refreshed.attempts == 2
        await session.execute(text("DELETE FROM jobs WHERE id = :i"), {"i": row.id})
        await session.commit()


async def test_single_attempt_still_fails_plain() -> None:
    job_type = _register_flaky(max_attempts=1, fail_times=99)
    row = await _insert_job(job_type)
    await runner.execute_job(str(row.id))
    async with session_factory() as session:
        refreshed = await session.get(Job, row.id)
        assert refreshed.status == JobStatus.FAILED
        await session.execute(text("DELETE FROM jobs WHERE id = :i"), {"i": row.id})
        await session.commit()


async def test_sweep_frees_stale_queued() -> None:
    from app.jobs.tasks import sweep_stale_jobs

    async with session_factory() as session:
        stale_id = (
            await session.execute(
                text(
                    "INSERT INTO jobs (id, type, status, created_at, dedup_key) "
                    "VALUES (:i, 'system.heartbeat', 'queued', now() - interval '1 hour', "
                    ":d) RETURNING id"
                ),
                {"i": uuid_module.uuid4(), "d": f"test-sweep-{uuid_module.uuid4().hex[:8]}"},
            )
        ).scalar_one()
        await session.commit()

    class Ctx:
        payload: dict = {}

        async def set_progress(self, *a, **k) -> None:  # type: ignore[no-untyped-def]
            return None

    result = await sweep_stale_jobs(Ctx())  # type: ignore[arg-type]
    assert result["swept"] >= 1
    async with session_factory() as session:
        status = (
            await session.execute(
                text("SELECT status FROM jobs WHERE id = :i"), {"i": stale_id}
            )
        ).scalar_one()
        await session.execute(text("DELETE FROM jobs WHERE id = :i"), {"i": stale_id})
        await session.commit()
    assert status == "failed"


async def test_requeue_endpoint(api_client, make_user) -> None:  # type: ignore[no-untyped-def]
    admin_user = await make_user("admin")
    employee = await make_user("employee")
    admin = login_headers(api_client, admin_user.email)

    async with session_factory() as session:
        dead_id = (
            await session.execute(
                text(
                    "INSERT INTO jobs (id, type, status, attempts, error) "
                    "VALUES (:i, 'system.heartbeat', 'dead', 3, 'proves') RETURNING id"
                ),
                {"i": uuid_module.uuid4()},
            )
        ).scalar_one()
        ok_id = (
            await session.execute(
                text(
                    "INSERT INTO jobs (id, type, status) "
                    "VALUES (:i, 'system.heartbeat', 'success') RETURNING id"
                ),
                {"i": uuid_module.uuid4()},
            )
        ).scalar_one()
        await session.commit()

    # Safata: llistat per estat amb sync:read (employee en té? employee → 403 al requeue).
    listing = api_client.get("/api/v1/jobs", params={"status": "dead"}, headers=admin)
    assert listing.status_code == 200, listing.text
    assert any(row["id"] == str(dead_id) for row in listing.json()["data"])

    assert (
        api_client.post(
            f"/api/v1/jobs/{dead_id}/actions/requeue",
            headers=login_headers(api_client, employee.email),
        ).status_code
        == 403
    )
    requeued = api_client.post(f"/api/v1/jobs/{dead_id}/actions/requeue", headers=admin)
    assert requeued.status_code == 202, requeued.text
    assert requeued.json()["status"] == "queued"
    assert requeued.json()["attempts"] == 0

    # Un job amb èxit no es re-encua.
    assert (
        api_client.post(f"/api/v1/jobs/{ok_id}/actions/requeue", headers=admin).status_code
        == 409
    )

    async with session_factory() as session:
        await session.execute(
            text("DELETE FROM jobs WHERE id IN (:a, :b)"), {"a": dead_id, "b": ok_id}
        )
        await session.commit()
