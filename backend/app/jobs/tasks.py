"""Handlers de jobs de la Fase 0.

Els jobs de negoci (sync, enriquiment, IA) arriben amb les seves fases;
aquí només hi ha el heartbeat que prova la maquinària de punta a punta.
"""

from datetime import UTC, datetime
from typing import Any

import app.integrations.pscp.enrich  # noqa: F401 — registra enrich.contract/batch
import app.integrations.socrata.sync  # noqa: F401 — registra sync.contracts
import app.integrations.socrata.sync_cpv  # noqa: F401 — registra sync.cpv
import app.integrations.socrata.sync_rpc  # noqa: F401 — registra extensions i menors
import app.modules.contracts.alerts  # noqa: F401 — registra alerts.recompute
from app.jobs.registry import JobContext, job


@job("system.heartbeat")
async def heartbeat(ctx: JobContext) -> dict[str, Any]:
    await ctx.set_progress(50, "Comprovant la maquinària")
    return {"beat_at": datetime.now(UTC).isoformat()}
