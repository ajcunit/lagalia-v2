"""Scheduler de procés únic (docker compose: `python -m app.jobs.scheduler`).

Encara que s'aixequin rèpliques, només la que té l'advisory lock de
PostgreSQL encua treballs; la resta queda en standby i pren el relleu
si la primera cau (resol el defecte v1 d'un scheduler per rèplica).
"""

import asyncio

import structlog
from redis.asyncio import Redis
from sqlalchemy import text

import app.jobs.tasks  # noqa: F401 — registra els handlers
from app.core.config import settings
from app.core.db import engine, session_factory
from app.core.logging import configure_logging
from app.jobs.schedule import SCHEDULE
from app.jobs.service import enqueue_job

logger = structlog.get_logger()

SCHEDULER_LOCK_KEY = 420_100
_TICK_SECONDS = 5
_STANDBY_SECONDS = 15


async def _tick(redis: Redis) -> None:
    for item in SCHEDULE:
        # SET NX amb caducitat = interval: com a molt un encuament per finestra.
        due = await redis.set(f"sched:{item.job_type}", "1", nx=True, ex=item.interval_seconds)
        if not due:
            continue
        async with session_factory() as session:
            try:
                job = await enqueue_job(session, job_type=item.job_type, dedup_key=item.dedup_key)
                logger.info("scheduled_job_enqueued", job_type=item.job_type, job_id=str(job.id))
            except Exception as exc:
                logger.error("scheduled_job_failed", job_type=item.job_type, error=str(exc))


async def main() -> None:
    configure_logging(settings.log_level, settings.log_format)
    redis = Redis.from_url(settings.redis_url)

    # Connexió dedicada: l'advisory lock de sessió viu mentre visqui ella.
    async with engine.connect() as lock_connection:
        while True:
            has_lock = (
                await lock_connection.execute(
                    text("SELECT pg_try_advisory_lock(:key)"), {"key": SCHEDULER_LOCK_KEY}
                )
            ).scalar_one()
            if has_lock:
                break
            logger.info("scheduler_standby")
            await asyncio.sleep(_STANDBY_SECONDS)

        logger.info("scheduler_active", schedule=[s.job_type for s in SCHEDULE])
        while True:
            await _tick(redis)
            await asyncio.sleep(_TICK_SECONDS)


if __name__ == "__main__":
    asyncio.run(main())
