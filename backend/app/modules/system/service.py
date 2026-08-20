"""Comprovacions d'estat del sistema (specs/system-status.md, B-022).

La distinció clau és «el procés existeix» vs «el servei fa la seva feina»:
un contenidor pot constar com a running amb el procés en crash-loop. Per
això el worker es prova per l'edat de l'últim heartbeat EXECUTAT i el
scheduler pel seu últim tick, no per cap ping de procés.

Aquí només hi ha infraestructura interna del compose (BD, Redis, MinIO):
els connectors externs es comproven al job de fons, mai dins d'una request.
"""

import asyncio
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings

CheckStatus = Literal["ok", "degraded", "failing"]

# Per sota d'això, la latència és normal; per sobre, el servei respon però
# malament (degraded). L'error o el timeout són failing.
LATENCY_DEGRADED_MS = 500

# El scheduler escriu aquesta clau a Redis a cada tick (5 s).
SCHEDULER_TICK_KEY = "system:scheduler_tick"
# El job de fons hi desa l'ús de l'emmagatzematge d'objectes.
STORAGE_USAGE_SETTING = "system.storage_usage"

# El heartbeat corre cada 300 s: dues finestres perdudes ja és sospitós,
# sis és que el worker no executa res.
WORKER_OK_SECONDS = 900
WORKER_DEGRADED_SECONDS = 1800

SCHEDULER_OK_SECONDS = 60
SCHEDULER_DEGRADED_SECONDS = 300


class ServiceCheck(BaseModel):
    name: str
    status: CheckStatus
    detail: str | None = None
    latency_ms: int | None = None
    checked_at: datetime | None = None


def worst_status(checks: list[ServiceCheck]) -> CheckStatus:
    order: dict[CheckStatus, int] = {"ok": 0, "degraded": 1, "failing": 2}
    worst: CheckStatus = "ok"
    for check in checks:
        if order[check.status] > order[worst]:
            worst = check.status
    return worst


def _latency_status(latency_ms: int) -> CheckStatus:
    return "ok" if latency_ms < LATENCY_DEGRADED_MS else "degraded"


def _age_status(age_seconds: float, ok_max: float, degraded_max: float) -> CheckStatus:
    if age_seconds <= ok_max:
        return "ok"
    if age_seconds <= degraded_max:
        return "degraded"
    return "failing"


async def check_database(session: AsyncSession) -> ServiceCheck:
    started = time.monotonic()
    try:
        await session.execute(text("SELECT 1"))
    except Exception as exc:
        return ServiceCheck(
            name="database", status="failing", detail=f"{type(exc).__name__}: {exc}"
        )
    latency = int((time.monotonic() - started) * 1000)
    return ServiceCheck(name="database", status=_latency_status(latency), latency_ms=latency)


async def database_size_bytes(session: AsyncSession) -> int | None:
    try:
        size = (
            await session.execute(text("SELECT pg_database_size(current_database())"))
        ).scalar_one()
        return int(size)
    except Exception:
        return None


async def redis_checks() -> tuple[ServiceCheck, ServiceCheck, int | None]:
    """PING (salut de Redis) + edat de l'últim tick del scheduler + memòria.

    Una sola connexió per a les tres coses; si Redis no respon, el
    scheduler tampoc no es pot avaluar (failing amb el mateix motiu).
    """
    client = Redis.from_url(settings.redis_url)
    try:
        started = time.monotonic()
        await client.ping()
        latency = int((time.monotonic() - started) * 1000)
        redis_check = ServiceCheck(
            name="redis", status=_latency_status(latency), latency_ms=latency
        )

        memory: int | None = None
        try:
            info = await client.info("memory")
            memory = int(info.get("used_memory", 0)) or None
        except Exception:
            memory = None

        raw_tick = await client.get(SCHEDULER_TICK_KEY)
        scheduler_check = _scheduler_check_from_tick(raw_tick)
        return redis_check, scheduler_check, memory
    except Exception as exc:
        detail = f"{type(exc).__name__}: {exc}"
        return (
            ServiceCheck(name="redis", status="failing", detail=detail),
            ServiceCheck(name="scheduler", status="failing", detail="Redis no respon"),
            None,
        )
    finally:
        await client.aclose()


def _scheduler_check_from_tick(raw_tick: bytes | None) -> ServiceCheck:
    if raw_tick is None:
        return ServiceCheck(
            name="scheduler", status="failing", detail="cap tick registrat: no ha arrencat mai"
        )
    try:
        tick_at = datetime.fromisoformat(raw_tick.decode())
    except ValueError:
        return ServiceCheck(name="scheduler", status="failing", detail="tick il·legible")
    age = (datetime.now(UTC) - tick_at).total_seconds()
    return ServiceCheck(
        name="scheduler",
        status=_age_status(age, SCHEDULER_OK_SECONDS, SCHEDULER_DEGRADED_SECONDS),
        detail=f"últim tick fa {int(age)} s",
        checked_at=tick_at,
    )


async def check_storage() -> ServiceCheck:
    started = time.monotonic()
    try:
        if settings.storage_backend == "s3":
            from app.core.storage import S3Storage

            storage = S3Storage()
            await asyncio.to_thread(storage._client.head_bucket, Bucket=storage._bucket)
        else:
            path = Path(settings.storage_local_path)
            await asyncio.to_thread(path.mkdir, parents=True, exist_ok=True)
    except Exception as exc:
        return ServiceCheck(name="storage", status="failing", detail=f"{type(exc).__name__}: {exc}")
    latency = int((time.monotonic() - started) * 1000)
    return ServiceCheck(name="storage", status=_latency_status(latency), latency_ms=latency)


async def check_worker(session: AsyncSession) -> ServiceCheck:
    """El worker es demostra viu executant: edat de l'últim heartbeat acabat."""
    last = (
        await session.execute(
            text(
                "SELECT finished_at FROM jobs "
                "WHERE type = 'system.heartbeat' AND status = 'success' "
                "AND finished_at IS NOT NULL ORDER BY finished_at DESC LIMIT 1"
            )
        )
    ).scalar_one_or_none()
    if last is None:
        return ServiceCheck(name="worker", status="failing", detail="cap heartbeat executat mai")
    age = (datetime.now(UTC) - last).total_seconds()
    return ServiceCheck(
        name="worker",
        status=_age_status(age, WORKER_OK_SECONDS, WORKER_DEGRADED_SECONDS),
        detail=f"últim heartbeat fa {int(age // 60)} min",
        checked_at=last,
    )
