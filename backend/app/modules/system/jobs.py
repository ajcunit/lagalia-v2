"""Job de fons de l'estat del sistema (specs/system-status.md, B-022).

Tot el que és lent o toca serveis externs viu aquí, mai a la request:
healthchecks dels connectors habilitats i mesura de l'ús de l'storage.
"""

import asyncio
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select

from app.core.config import settings
from app.core.db import session_factory
from app.integrations import hub
from app.integrations.models import ConnectorRecord
from app.jobs.registry import JobContext, job
from app.modules.config.models import Setting
from app.modules.system.service import STORAGE_USAGE_SETTING

logger = structlog.get_logger()

# Límit de la mesura: prou per a l'entorn actual; més enllà es trunca i es
# marca, mai es fa una passada il·limitada (l'S3 no té un «total» barat).
MAX_OBJECT_PAGES = 10


async def _refresh_connector_health() -> dict[str, int]:
    refreshed = 0
    failing = 0
    async with session_factory() as session:
        records = list(
            (
                await session.execute(
                    select(ConnectorRecord).where(ConnectorRecord.enabled.is_(True))
                )
            ).scalars()
        )
        for record in records:
            try:
                connector = await hub.get_connector(session, record.slug)
                health = await connector.healthcheck()
                record.health_status = "healthy" if health.healthy else "failing"
                if not health.healthy:
                    failing += 1
            except Exception as exc:  # un connector caigut no atura la resta
                record.health_status = "failing"
                failing += 1
                logger.warning("status_snapshot_connector_failed", slug=record.slug, error=str(exc))
            record.last_health_check = datetime.now(UTC)
            refreshed += 1
        await session.commit()
    return {"connectors": refreshed, "connectors_failing": failing}


def _measure_s3() -> dict[str, Any]:
    from app.core.storage import S3Storage

    storage = S3Storage()
    paginator = storage._client.get_paginator("list_objects_v2")
    objects = 0
    total_bytes = 0
    truncated = False
    for index, page in enumerate(paginator.paginate(Bucket=storage._bucket), start=1):
        for item in page.get("Contents", []):
            objects += 1
            total_bytes += int(item.get("Size", 0))
        if index >= MAX_OBJECT_PAGES:
            truncated = bool(page.get("IsTruncated"))
            break
    return {"objects": objects, "total_bytes": total_bytes, "truncated": truncated}


def _measure_filesystem() -> dict[str, Any]:
    from pathlib import Path

    base = Path(settings.storage_local_path)
    objects = 0
    total_bytes = 0
    if base.exists():
        for path in base.rglob("*"):
            if path.is_file():
                objects += 1
                total_bytes += path.stat().st_size
    return {"objects": objects, "total_bytes": total_bytes, "truncated": False}


async def _store_usage(usage: dict[str, Any]) -> None:
    usage["measured_at"] = datetime.now(UTC).isoformat()
    async with session_factory() as session:
        setting = (
            await session.execute(select(Setting).where(Setting.key == STORAGE_USAGE_SETTING))
        ).scalar_one_or_none()
        if setting is None:
            session.add(Setting(key=STORAGE_USAGE_SETTING, value=usage))
        else:
            setting.value = usage
        await session.commit()


@job("system.status_snapshot")
async def status_snapshot(ctx: JobContext) -> dict[str, Any]:
    result = await _refresh_connector_health()
    try:
        measure = _measure_s3 if settings.storage_backend == "s3" else _measure_filesystem
        usage = await asyncio.to_thread(measure)
        await _store_usage(usage)
        result["storage_objects"] = int(usage["objects"])
    except Exception as exc:  # la mesura no és crítica: es reintenta al següent
        logger.warning("status_snapshot_storage_failed", error=str(exc))
    return result
