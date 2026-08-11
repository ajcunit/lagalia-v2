"""Rate limiting amb comptadors a Redis (INCR + EXPIRE).

Si Redis no respon, el limitador s'obre i ho registra: la disponibilitat
del login preval i la mitigació addicional és a la capa de proxy.
"""

import structlog
from redis import RedisError
from redis.asyncio import Redis

from app.core.config import settings
from app.core.problems import Problem

logger = structlog.get_logger()

_WINDOWS = {"second": 1, "minute": 60, "hour": 3600, "day": 86400}


def parse_rate(rate: str) -> tuple[int, int]:
    """'5/minute' → (5, 60)."""
    count, _, unit = rate.partition("/")
    return int(count), _WINDOWS[unit]


async def enforce_rate_limit(scope: str, key: str, limit: int, window_seconds: int) -> None:
    """Aixeca Problem 429 amb Retry-After si (scope, key) supera el límit.

    El client es crea per crida: un client global quedaria lligat a
    l'event loop de la primera petició.
    """
    redis_key = f"rl:{scope}:{key}"
    client = Redis.from_url(settings.redis_url)
    try:
        current = await client.incr(redis_key)
        if current == 1:
            await client.expire(redis_key, window_seconds)
        if current > limit:
            ttl = await client.ttl(redis_key)
            retry_after = ttl if ttl > 0 else window_seconds
            raise Problem(
                429,
                "Massa peticions",
                "rate-limited",
                headers={"Retry-After": str(retry_after)},
            )
    except RedisError:
        logger.error("rate_limit_backend_unavailable", scope=scope)
    finally:
        await client.aclose()
