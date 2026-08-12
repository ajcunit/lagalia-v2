"""Esdeveniments de progrés a Redis (pub/sub), consumits per l'SSE.

Mai s'hi publica el payload del job: només estat, progrés i resultat.
"""

import json
import uuid
from typing import Any

from redis.asyncio import Redis

from app.core.config import settings
from app.jobs.models import Job


def channel_for(job_id: uuid.UUID) -> str:
    return f"job:{job_id}:events"


def snapshot(job: Job) -> dict[str, Any]:
    return {
        "id": str(job.id),
        "type": job.type,
        "status": job.status.value,
        "progress": job.progress,
        "progress_message": job.progress_message,
        "result": job.result,
        "error": job.error,
    }


async def publish_event(job_id: uuid.UUID, payload: dict[str, Any]) -> None:
    client = Redis.from_url(settings.redis_url)
    try:
        await client.publish(channel_for(job_id), json.dumps(payload))
    finally:
        await client.aclose()
