"""Escriptura d'entrades a audit_log amb cadena de hash.

entry_hash = sha256(prev_hash || payload canònic). L'advisory lock
serialitza els appends perquè la cadena no es bifurqui sota concurrència.
"""

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.models import AuditActorType, AuditLogEntry

# Identificador arbitrari però estable de l'advisory lock d'aquesta taula.
_AUDIT_LOCK_KEY = 420_001


async def record_audit(
    session: AsyncSession,
    *,
    actor_type: AuditActorType,
    action: str,
    success: bool,
    actor_id: int | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
    trace_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> AuditLogEntry:
    await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _AUDIT_LOCK_KEY})

    prev_hash = (
        await session.execute(
            select(AuditLogEntry.entry_hash).order_by(AuditLogEntry.id.desc()).limit(1)
        )
    ).scalar_one_or_none()

    occurred_at = datetime.now(UTC)
    payload = json.dumps(
        {
            "occurred_at": occurred_at.isoformat(),
            "actor_type": actor_type.value,
            "actor_id": actor_id,
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "ip": ip,
            "trace_id": trace_id,
            "details": details,
            "success": success,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    entry_hash = hashlib.sha256(f"{prev_hash or ''}|{payload}".encode()).hexdigest()

    entry = AuditLogEntry(
        occurred_at=occurred_at,
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        ip=ip,
        user_agent=user_agent,
        trace_id=trace_id,
        details=details,
        success=success,
        prev_hash=prev_hash,
        entry_hash=entry_hash,
    )
    session.add(entry)
    await session.flush()
    return entry
