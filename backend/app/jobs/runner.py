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
from app.jobs.registry import JobContext, get_handler

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
        await _finish(job_id, JobStatus.FAILED, error=f"{type(exc).__name__}: {exc}")
        log.error("job_failed", error=str(exc))
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
