"""Worker d'arq (docker compose: `arq app.jobs.worker.WorkerSettings`)."""

from typing import Any

import structlog
from arq.connections import RedisSettings

import app.jobs.tasks  # noqa: F401 — registra els handlers
from app.core.config import settings
from app.core.logging import configure_logging
from app.jobs import runner

logger = structlog.get_logger()


async def execute_job(_ctx: dict[str, Any], job_row_id: str) -> None:
    await runner.execute_job(job_row_id)


async def startup(_ctx: dict[str, Any]) -> None:
    configure_logging(settings.log_level, settings.log_format)
    logger.info("worker_started", environment=settings.environment)


async def shutdown(_ctx: dict[str, Any]) -> None:
    logger.info("worker_stopped")


class WorkerSettings:
    functions = [execute_job]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    allow_abort_jobs = True
    max_tries = 1  # reintents amb backoff: backlog B-009
