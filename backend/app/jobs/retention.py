"""Retenció i purga de dades (specs/data-retention.md, B-006).

Valors per defecte de 06-seguretat §7 (auditoria 2 anys, IA 1 any),
configurables per settings segons les indicacions del DPO. Job diari.
"""

from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import session_factory
from app.jobs.registry import JobContext, job

logger = structlog.get_logger()

SETTING_AUDIT_DAYS = "retention.audit_log_days"
SETTING_AI_DAYS = "retention.ai_days"

DEFAULT_AUDIT_DAYS = 730  # 2 anys (06-seguretat §7)
DEFAULT_AI_DAYS = 365  # 1 any: ai_runs i converses de xat


def parse_retention_days(raw: Any, *, default: int) -> int:
    """Dies de retenció; invàlid o fora de rang (30-3650) = per defecte.

    El mínim de 30 evita que un error de configuració buidi l'auditoria.
    """
    try:
        days = int(str(raw).strip())
    except (ValueError, TypeError):
        return default
    return days if 30 <= days <= 3650 else default


async def _load_days(session: AsyncSession) -> tuple[int, int]:
    from sqlalchemy import select

    from app.modules.config.models import Setting

    rows = (
        await session.execute(
            select(Setting.key, Setting.value).where(
                Setting.key.in_([SETTING_AUDIT_DAYS, SETTING_AI_DAYS])
            )
        )
    ).all()
    values = {row.key: row.value for row in rows}
    return (
        parse_retention_days(values.get(SETTING_AUDIT_DAYS), default=DEFAULT_AUDIT_DAYS),
        parse_retention_days(values.get(SETTING_AI_DAYS), default=DEFAULT_AI_DAYS),
    )


@job("retention.purge")
async def purge(ctx: JobContext) -> dict[str, Any]:
    async with session_factory() as session:
        audit_days, ai_days = await _load_days(session)

        def older_than(days: int) -> str:
            return f"now() - interval '{int(days)} days'"

        # Porta sancionada del trigger append-only (migració 0034): només
        # aquesta transacció pot esborrar auditoria, i només files caducades.
        await session.execute(text("SET LOCAL app.retention_purge = 'on'"))
        # Només el PREFIX de la cadena de hashos: mai una fila amb entrades
        # posteriors per id (una fila del mig trencaria l'enllaç prev_hash
        # de la següent). Amb occurred_at monòton són el mateix conjunt.
        audit_deleted = (
            await session.execute(
                text(
                    "DELETE FROM audit_log WHERE occurred_at < " + older_than(audit_days) + " "
                    "AND id < COALESCE((SELECT min(id) FROM audit_log "
                    "WHERE occurred_at >= " + older_than(audit_days) + "), "
                    "(SELECT COALESCE(max(id), 0) + 1 FROM audit_log))"
                )
            )
        ).rowcount
        ai_runs_deleted = (
            await session.execute(
                text("DELETE FROM ai_runs WHERE created_at < " + older_than(ai_days))
            )
        ).rowcount
        # Converses: missatges vells fora; els fils que queden buits, també.
        chat_messages_deleted = (
            await session.execute(
                text("DELETE FROM chat_messages WHERE created_at < " + older_than(ai_days))
            )
        ).rowcount
        chat_threads_deleted = (
            await session.execute(
                text(
                    "DELETE FROM chat_threads t WHERE NOT EXISTS "
                    "(SELECT 1 FROM chat_messages m WHERE m.thread_id = t.id) "
                    "AND t.created_at < " + older_than(ai_days)
                )
            )
        ).rowcount

        # La purga també deixa rastre — via record_audit, que manté la
        # cadena de hashos (l'INSERT cru la trencaria). Esborrar el
        # començament de la cadena és segur: el verificador ancora la
        # primera entrada disponible tal qual.
        from app.modules.audit.models import AuditActorType
        from app.modules.audit.service import record_audit

        await record_audit(
            session,
            actor_type=AuditActorType.SYSTEM,
            action="retention.purge",
            success=True,
            details={
                "audit_log": audit_deleted,
                "ai_runs": ai_runs_deleted,
                "chat_messages": chat_messages_deleted,
                "chat_threads": chat_threads_deleted,
                "audit_days": audit_days,
                "ai_days": ai_days,
            },
        )
        await session.commit()

    result = {
        "audit_log": audit_deleted,
        "ai_runs": ai_runs_deleted,
        "chat_messages": chat_messages_deleted,
        "chat_threads": chat_threads_deleted,
        "audit_days": audit_days,
        "ai_days": ai_days,
    }
    logger.info("retention_purged", **result)
    return result
