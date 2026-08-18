"""Handlers de jobs de la Fase 0.

Els jobs de negoci (sync, enriquiment, IA) arriben amb les seves fases;
aquí només hi ha el heartbeat que prova la maquinària de punta a punta.
"""

from datetime import UTC, datetime
from typing import Any

import app.ai.legal_corpus  # noqa: F401 — registra sync.boe_norms
import app.ai.project_refs  # noqa: F401 — registra docgen.index_external/purge_expired
import app.ai.rag  # noqa: F401 — registra rag.index
import app.ai.scheduled_reports  # noqa: F401 — registra reports.audit_monthly
import app.integrations.boe.connector  # noqa: F401 — registra el connector boe
import app.integrations.field_mappings  # noqa: F401 — registra sync.remap_contracts
import app.integrations.ldap.connector  # noqa: F401 — registra el connector ldap
import app.jobs.nightly  # noqa: F401 — registra sync.nightly
import app.integrations.pscp.enrich  # noqa: F401 — registra enrich.contract/batch
import app.integrations.smtp.connector  # noqa: F401 — registra el connector smtp
import app.integrations.socrata.sync  # noqa: F401 — registra sync.contracts
import app.integrations.socrata.sync_cpv  # noqa: F401 — registra sync.cpv
import app.integrations.socrata.sync_execution  # noqa: F401 — registra sync.execution
import app.integrations.socrata.sync_rpc  # noqa: F401 — registra extensions i menors
import app.modules.contractors.jobs  # noqa: F401 — registra contractors.consolidate
import app.modules.contracts.alerts  # noqa: F401 — registra alerts.recompute
import app.modules.contracts.exports  # noqa: F401 — registra export.contracts
import app.modules.tasks.reminders  # noqa: F401 — registra tasks.reminders
import app.modules.webhooks.jobs  # noqa: F401 — registra webhooks.dispatch
from app.jobs.registry import JobContext, job


@job("system.heartbeat")
async def heartbeat(ctx: JobContext) -> dict[str, Any]:
    await ctx.set_progress(50, "Comprovant la maquinària")
    return {"beat_at": datetime.now(UTC).isoformat()}


@job("jobs.sweep")
async def sweep_stale_jobs(ctx: JobContext) -> dict[str, Any]:
    """Escombrat B-009: jobs `queued` estancats (mai arrencats en 30 min)
    passen a `failed` i alliberen el seu dedup_key. Cas real: un worker antic
    sense el handler deixava el job zombi i bloquejava tots els encuaments."""
    from sqlalchemy import text

    from app.core.db import session_factory

    async with session_factory() as session:
        result = await session.execute(
            text(
                "UPDATE jobs SET status = 'failed', finished_at = now(), "
                "error = 'estancat: mai arrencat en 30 minuts (escombrat B-009)' "
                "WHERE status = 'queued' AND started_at IS NULL "
                "AND created_at < now() - interval '30 minutes' "
                "AND type <> 'jobs.sweep'"
            )
        )
        await session.commit()
    return {"swept": result.rowcount or 0}
