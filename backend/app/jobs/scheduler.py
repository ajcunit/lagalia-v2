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
    await _tick_nightly(redis)
    await _tick_reports(redis)


async def _tick_reports(redis: Redis) -> None:
    """Informe d'auditoria programat: activable i amb cadència configurable
    (specs/ai-refinements.md). Desactivat de sèrie."""
    from sqlalchemy import select

    from app.jobs.nightly import parse_enabled, parse_interval_days
    from app.modules.config.models import Setting

    async with session_factory() as session:
        rows = (
            await session.execute(
                select(Setting.key, Setting.value).where(
                    Setting.key.in_(["reports.audit_enabled", "reports.audit_interval_days"])
                )
            )
        ).all()
    values = {row.key: row.value for row in rows}
    # Sense el setting = desactivat: mai s'envia un informe que ningú ha demanat.
    if not parse_enabled(values.get("reports.audit_enabled"), default=False):
        return
    interval_days = parse_interval_days(values.get("reports.audit_interval_days"), default=30)
    due = await redis.set(
        "sched:reports.audit_monthly", "1", nx=True, ex=interval_days * 86400
    )
    if not due:
        return
    async with session_factory() as session:
        try:
            job = await enqueue_job(
                session, job_type="reports.audit_monthly", dedup_key="reports.audit_monthly"
            )
            logger.info("audit_report_enqueued", job_id=str(job.id), interval_days=interval_days)
        except Exception as exc:
            logger.error("audit_report_failed", error=str(exc))


async def _tick_nightly(redis: Redis) -> None:
    """Cadena nocturna configurable (specs/sync-schedule.md): la config es
    llegeix de la BD a cada tick, així canviar l'hora no demana reinici."""
    from datetime import UTC, datetime

    from app.jobs import nightly

    async with session_factory() as session:
        values = await nightly.load_schedule_settings(session)
    now = datetime.now(UTC)
    if not nightly.nightly_due(
        now,
        enabled_raw=values.get(nightly.SETTING_ENABLED),
        time_raw=values.get(nightly.SETTING_TIME),
        days_raw=values.get(nightly.SETTING_DAYS),
    ):
        return
    local_date = now.astimezone(nightly.TIMEZONE).date().isoformat()
    # Un dispar per dia local, encara que hi hagi molts ticks (26 h de marge
    # perquè la clau no caduqui abans del tomb de dia).
    due = await redis.set(f"sched:sync.nightly:{local_date}", "1", nx=True, ex=26 * 3600)
    if not due:
        return
    async with session_factory() as session:
        try:
            job = await enqueue_job(
                session, job_type="sync.nightly", dedup_key="sync.nightly"
            )
            logger.info("nightly_sync_enqueued", job_id=str(job.id), date=local_date)
        except Exception as exc:
            logger.error("nightly_sync_failed", error=str(exc))


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
