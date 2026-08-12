"""Tokens efímers d'un sol ús per a SSE i descàrregues (05-api.md §2).

Opacs, 60 segons de vida, lligats a {usuari, propòsit, recurs} i
consumits atòmicament amb GETDEL: mai un JWT per query string.
"""

import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from redis.asyncio import Redis

from app.core.config import settings

TTL_SECONDS = 60


@dataclass(frozen=True)
class EphemeralGrant:
    user_id: int
    purpose: str
    resource: str


async def issue_token(user_id: int, purpose: str, resource: str) -> tuple[str, datetime]:
    token = secrets.token_urlsafe(32)
    client = Redis.from_url(settings.redis_url)
    try:
        await client.setex(
            f"eph:{token}",
            TTL_SECONDS,
            json.dumps({"user_id": user_id, "purpose": purpose, "resource": resource}),
        )
    finally:
        await client.aclose()
    return token, datetime.now(UTC) + timedelta(seconds=TTL_SECONDS)


async def consume_token(token: str) -> EphemeralGrant | None:
    """Un sol ús: el GETDEL garanteix que el segon consumidor no rep res."""
    client = Redis.from_url(settings.redis_url)
    try:
        raw = await client.getdel(f"eph:{token}")
    finally:
        await client.aclose()
    if raw is None:
        return None
    data = json.loads(raw)
    return EphemeralGrant(
        user_id=data["user_id"], purpose=data["purpose"], resource=data["resource"]
    )
