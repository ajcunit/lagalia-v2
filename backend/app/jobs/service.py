"""Casos d'ús de jobs: encuar, consultar, cancel·lar.

Accés: el creador sempre; per a la resta, les concessions sync:read
(consulta) i sync:execute (cancel·lació) de la matriu A2 — cap check
de rol fora del motor.
"""

import uuid
from typing import Any

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings
from arq.jobs import Job as ArqJob
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import authz
from app.core.config import settings
from app.core.problems import Problem
from app.jobs import events
from app.jobs.models import Job, JobStatus
from app.jobs.registry import get_handler
from app.modules.audit.models import AuditActorType
from app.modules.audit.service import record_audit
from app.modules.users.models import User
from app.modules.users.service import RequestContext


async def _arq_pool() -> ArqRedis:
    return await create_pool(RedisSettings.from_dsn(settings.redis_url))


async def enqueue_job(
    session: AsyncSession,
    *,
    job_type: str,
    payload: dict[str, Any] | None = None,
    created_by: int | None = None,
    dedup_key: str | None = None,
) -> Job:
    get_handler(job_type)  # tipus desconegut = error de programació, no de dades

    job = Job(type=job_type, payload=payload, created_by=created_by, dedup_key=dedup_key)
    session.add(job)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise Problem(409, "Ja hi ha un treball equivalent en curs", "conflict") from None

    pool = await _arq_pool()
    try:
        await pool.enqueue_job(
            "execute_job",
            str(job.id),
            _job_id=str(job.id),
            _queue_name=settings.jobs_queue_name,
        )
    finally:
        await pool.aclose()
    await session.commit()
    return job


async def _load_job(session: AsyncSession, job_id: uuid.UUID) -> Job:
    job = await session.get(Job, job_id)
    if job is None:
        raise Problem(404, "Treball no trobat", "not-found")
    return job


async def _require_access(
    session: AsyncSession, job: Job, user: User, action: str, ctx: RequestContext
) -> None:
    if job.created_by == user.id or authz.evaluate(user, action) is not None:
        return
    await record_audit(
        session,
        actor_type=AuditActorType.USER,
        action="authz.denied",
        success=False,
        actor_id=user.id,
        resource_type="job",
        resource_id=str(job.id),
        ip=ctx.ip,
        user_agent=ctx.user_agent,
        trace_id=ctx.trace_id,
        details={"action": action},
    )
    await session.commit()
    raise Problem(403, "Sense permís per a aquest treball", "forbidden")


async def get_job_for(
    session: AsyncSession, job_id: uuid.UUID, user: User, ctx: RequestContext
) -> Job:
    job = await _load_job(session, job_id)
    await _require_access(session, job, user, "sync:read", ctx)
    return job


def can_read_job(job: Job, user: User) -> bool:
    return job.created_by == user.id or authz.evaluate(user, "sync:read") is not None


async def cancel_job(
    session: AsyncSession, job_id: uuid.UUID, user: User, ctx: RequestContext
) -> Job:
    job = await _load_job(session, job_id)
    await _require_access(session, job, user, "sync:execute", ctx)

    if job.status.is_terminal:
        raise Problem(409, "El treball ja ha acabat", "conflict")

    pool = await _arq_pool()
    try:
        # Best-effort: si ja corre, el worker rebrà l'abort i marcarà
        # cancelled; si encara no, l'estat de la fila mana.
        await ArqJob(str(job.id), redis=pool).abort(timeout=1)
    except Exception:  # noqa: S110
        pass
    finally:
        await pool.aclose()

    if job.status == JobStatus.QUEUED:
        # Encara no ha arrencat: el runner el saltarà; el marquem ja.
        job.status = JobStatus.CANCELLED
        await session.flush()
        await events.publish_event(job.id, events.snapshot(job))

    await record_audit(
        session,
        actor_type=AuditActorType.USER,
        action="jobs.cancel",
        success=True,
        actor_id=user.id,
        resource_type="job",
        resource_id=str(job.id),
        ip=ctx.ip,
        user_agent=ctx.user_agent,
        trace_id=ctx.trace_id,
    )
    await session.commit()
    return job
