"""Generació i verificació d'API keys (specs/service-accounts.md)."""

import hashlib
import secrets
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.service_accounts.models import ServiceAccount

KEY_PREFIX = "sk_"


def generate_key() -> str:
    return KEY_PREFIX + secrets.token_urlsafe(32)


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


async def resolve_key(session: AsyncSession, key: str) -> ServiceAccount | None:
    """Clau → compte actiu i no caducat; registra l'últim ús."""
    account = (
        await session.execute(
            select(ServiceAccount).where(ServiceAccount.key_hash == hash_key(key))
        )
    ).scalar_one_or_none()
    if account is None or not account.active:
        return None
    now = datetime.now(UTC)
    if account.expires_at is not None and account.expires_at <= now:
        return None
    # last_used_at amb granularitat de minut per no escriure a cada petició.
    if account.last_used_at is None or (now - account.last_used_at).total_seconds() > 60:
        account.last_used_at = now
        await session.flush()
    return account
