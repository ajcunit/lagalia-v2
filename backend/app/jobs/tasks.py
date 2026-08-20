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
import app.integrations.pscp.enrich  # noqa: F401 — registra enrich.contract/batch
import app.integrations.smtp.connector  # noqa: F401 — registra el connector smtp
import app.integrations.socrata.sync  # noqa: F401 — registra sync.contracts
import app.integrations.socrata.sync_cpv  # noqa: F401 — registra sync.cpv
import app.integrations.socrata.sync_execution  # noqa: F401 — registra sync.execution
import app.integrations.socrata.sync_rpc  # noqa: F401 — registra extensions i menors
import app.jobs.nightly  # noqa: F401 — registra sync.nightly
import app.jobs.retention  # noqa: F401 — registra retention.purge
import app.modules.bpm.jobs  # noqa: F401 — registra bpm.scan
import app.modules.contractors.jobs  # noqa: F401 — registra contractors.consolidate
import app.modules.contracts.alerts  # noqa: F401 — registra alerts.recompute
import app.modules.contracts.exports  # noqa: F401 — registra export.contracts
import app.modules.system.jobs  # noqa: F401 — registra system.status_snapshot
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
    sense el handler deixava el job zombi i bloquejava tots els encuaments.

    B-021: tanca també les execucions de sincronització que van quedar
    «executant» perquè el seu job va morir sense poder-les tancar
    (cancel·lació, temps exhaurit, worker reiniciat)."""
    from sqlalchemy import text

    from app.core.config import settings
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
        # Un job «running» més vell que el temps límit del worker és
        # provadament mort: arq no deixa córrer res més enllà de
        # job_timeout, o sigui que si la fila continua així és que el
        # worker va morir (SIGKILL, OOM, redeploy) sense poder-la tancar.
        # Cas real: bloquejava el dedup_key i no es podia rellançar res.
        zombies = await session.execute(
            text(
                "UPDATE jobs SET status = 'failed', finished_at = now(), "
                "error = 'interromput: el worker va morir sense tancar el treball' "
                "WHERE status = 'running' "
                "AND started_at < now() - make_interval(secs => :deadline) "
                "AND type <> 'jobs.sweep'"
            ),
            {"deadline": settings.jobs_timeout_seconds + 1800},
        )
        # Amb vincle: el job ja és en un estat terminal, o ha desaparegut.
        # Sense vincle (execucions d'abans del vincle): per antiguitat.
        orphans = await session.execute(
            text(
                "UPDATE sync_runs r SET status = 'failed', finished_at = now(), "
                "error_summary = jsonb_build_object('error', CAST(:reason AS text)) "
                "WHERE r.status = 'running' AND ("
                "  (r.job_id IS NOT NULL AND NOT EXISTS ("
                "     SELECT 1 FROM jobs j WHERE j.id = r.job_id"
                "      AND j.status IN ('queued', 'running')))"
                "  OR (r.job_id IS NULL AND r.started_at < now() - interval '24 hours')"
                ")"
            ),
            {"reason": "interrompuda: el treball que l'executava ja no és viu (B-021)"},
        )
        await session.commit()
    return {
        "swept": int(getattr(result, "rowcount", 0) or 0),
        "zombies_failed": int(getattr(zombies, "rowcount", 0) or 0),
        "runs_closed": int(getattr(orphans, "rowcount", 0) or 0),
    }
