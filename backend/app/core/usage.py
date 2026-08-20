"""Comptadors d'ús de la plataforma (specs/usage-tracking.md, B-010).

Efímers a Redis, amb clau per dia UTC i 40 dies de TTL: prou per a la
pantalla d'administració sense cap taula ni migració. La capa de mètriques
Prometheus/Grafana de docs/03 §3 queda al backlog com a evolució.

El registre no pot trencar mai una request: qualsevol error de Redis
s'engoleix i es deixa al log.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from redis.asyncio import Redis

from app.core.config import settings

logger = structlog.get_logger()

RETENTION_SECONDS = 40 * 86400


def _redis() -> Redis:
    # Client per crida (mateix patró que events.publish_event): un client
    # cachejat queda lligat a l'event loop on neix i peta en silenci quan
    # el procés en fa servir un altre (tests, re-arrencades).
    client: Redis = Redis.from_url(settings.redis_url)
    return client


def _day_key(day: str, kind: str) -> str:
    return f"usage:{kind}:{day}"


async def record_request(method: str, route: str, status_code: int, user_id: int | None) -> None:
    """Compta una request per plantilla de ruta (mai el path cru: cardinalitat
    continguda i cap identificador de recurs als comptadors)."""
    try:
        day = datetime.now(UTC).date().isoformat()
        field = f"{method} {route}"
        client = _redis()
        try:
            pipe = client.pipeline(transaction=False)
            pipe.hincrby(_day_key(day, "api"), field, 1)
            pipe.expire(_day_key(day, "api"), RETENTION_SECONDS)
            if status_code >= 400:
                pipe.hincrby(_day_key(day, "errors"), field, 1)
                pipe.expire(_day_key(day, "errors"), RETENTION_SECONDS)
            if user_id is not None:
                pipe.hincrby(_day_key(day, "users"), str(user_id), 1)
                pipe.expire(_day_key(day, "users"), RETENTION_SECONDS)
            await pipe.execute()
        finally:
            await client.aclose()
    except Exception as exc:
        logger.warning("usage_tracking_failed", error=str(exc))


def _decode_counts(raw: dict[bytes, bytes]) -> dict[str, int]:
    return {key.decode(): int(value) for key, value in raw.items()}


async def _hgetall(client: Redis, key: str) -> dict[str, int]:
    # redis-py tipa hgetall com a unió sync/async segons el client: aquí és
    # sempre l'asíncron.
    raw: dict[bytes, bytes] = await client.hgetall(key)  # type: ignore[misc]
    return _decode_counts(raw)


async def read_usage(days: int) -> list[dict[str, Any]]:
    """Sèrie diària (avui inclòs, més recent primer) amb els comptadors crus."""
    client = _redis()
    try:
        today = datetime.now(UTC).date()
        series: list[dict[str, Any]] = []
        for offset in range(days):
            day = (today - timedelta(days=offset)).isoformat()
            endpoints = await _hgetall(client, _day_key(day, "api"))
            errors = await _hgetall(client, _day_key(day, "errors"))
            users = await _hgetall(client, _day_key(day, "users"))
            series.append(
                {
                    "day": day,
                    "requests": sum(endpoints.values()),
                    "errors": sum(errors.values()),
                    "endpoints": endpoints,
                    "endpoint_errors": errors,
                    "users": users,
                }
            )
        return series
    finally:
        await client.aclose()
