"""Execució d'un job: transicions d'estat, progrés i esdeveniments.

És l'única funció que el worker d'arq coneix; el handler concret surt
del registre segons el tipus desat a la fila.
"""

import asyncio
import uuid
from datetime import UTC, datetime

import structlog

from app.core.db import session_factory
from app.jobs import events
from app.jobs.models import Job, JobStatus
from app.jobs.registry import JobContext, get_handler, get_policy

logger = structlog.get_logger()


async def execute_job(job_row_id: str) -> None:
    job_id = uuid.UUID(job_row_id)

    async with session_factory() as session:
        job = await session.get(Job, job_id)
        if job is None:
            logger.error("job_row_missing", job_id=job_row_id)
            return
        if job.status != JobStatus.QUEUED:
            # Cancel·lat (o repetit) abans d'arrencar: no s'executa.
            logger.info("job_skipped", job_id=job_row_id, status=job.status.value)
            return
        job.status = JobStatus.RUNNING
        job.started_at = datetime.now(UTC)
        job.attempts += 1
        await session.commit()
        job_type, payload = job.type, job.payload

    await events.publish_event(job_id, {"status": "running", "progress": 0})
    log = logger.bind(job_id=job_row_id, job_type=job_type)
    log.info("job_started")

    async def set_progress(progress: int, message: str | None = None) -> None:
        async with session_factory() as progress_session:
            row = await progress_session.get(Job, job_id)
            if row is not None:
                row.progress = max(0, min(100, progress))
                row.progress_message = message
                await progress_session.commit()
        await events.publish_event(
            job_id, {"status": "running", "progress": progress, "progress_message": message}
        )

    try:
        handler = get_handler(job_type)
        result = await handler(
            JobContext(job_id=job_id, payload=payload, set_progress=set_progress)
        )
    except asyncio.CancelledError:
        await _finish(job_id, JobStatus.CANCELLED)
        log.info("job_cancelled")
        raise
    except Exception as exc:
        # Mai el payload a l'error: només el tipus i el missatge de l'excepció.
        policy = get_policy(job_type)
        async with session_factory() as session:
            row = await session.get(Job, job_id)
            attempts = row.attempts if row is not None else 1
        if attempts < policy.max_attempts:
            delay = policy.delay_for(attempts)
            await _retry_later(job_id, attempts, policy.max_attempts, delay, exc)
            log.warning(
                "job_retry_scheduled", attempt=attempts,
                max_attempts=policy.max_attempts, delay_seconds=delay, error=str(exc),
            )
            return
        terminal = JobStatus.DEAD if policy.max_attempts > 1 else JobStatus.FAILED
        await _finish(job_id, terminal, error=f"{type(exc).__name__}: {exc}")
        log.error("job_failed", terminal=terminal.value, error=str(exc))
        return

    await _finish(job_id, JobStatus.SUCCESS, result=result)
    log.info("job_finished")


async def _finish(
    job_id: uuid.UUID,
    status: JobStatus,
    *,
    result: dict[str, object] | None = None,
    error: str | None = None,
) -> None:
    async with session_factory() as session:
        job = await session.get(Job, job_id)
        if job is None:
            return
        job.status = status
        job.finished_at = datetime.now(UTC)
        if status == JobStatus.SUCCESS:
            job.progress = 100
        if result is not None:
            job.result = result
        if error is not None:
            job.error = error
        await session.commit()
        payload = events.snapshot(job)
    await events.publish_event(job_id, payload)


async def _retry_later(
    job_id: uuid.UUID, attempt: int, max_attempts: int, delay: int, exc: Exception
) -> None:
    """Reintent amb backoff (B-009): torna el job a la cua amb retard."""
    async with session_factory() as session:
        job = await session.get(Job, job_id)
        if job is None:
            return
        job.status = JobStatus.QUEUED
        job.error = f"{type(exc).__name__}: {exc}"
        job.progress = 0
        job.progress_message = (
            f"reintent {attempt + 1}/{max_attempts} d'aquí a {delay}s"
        )
        await session.commit()
    from app.jobs.service import enqueue_arq_retry

    await enqueue_arq_retry(job_id, attempt=attempt, delay_seconds=delay)
    await events.publish_event(
        job_id, {"status": "queued", "progress": 0, "attempt": attempt + 1}
    )
