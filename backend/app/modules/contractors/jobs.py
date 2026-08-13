"""Job contractors.consolidate (specs/contractor-normalization.md)."""

from typing import Any

import structlog

from app.core.db import session_factory
from app.jobs.registry import JobContext, job
from app.modules.audit.models import AuditActorType
from app.modules.audit.service import record_audit
from app.modules.contractors.service import consolidate_same_identity

logger = structlog.get_logger()


@job("contractors.consolidate")
async def consolidate_contractors(ctx: JobContext) -> dict[str, Any]:
    async with session_factory() as session:
        result = await consolidate_same_identity(session)
        await record_audit(
            session,
            actor_type=AuditActorType.SYSTEM,
            action="contractors.consolidate",
            success=True,
            resource_type="contractors",
            resource_id="consolidate",
            details=result,
        )
        await session.commit()
        from app.modules.webhooks.service import enqueue_dispatch

        await enqueue_dispatch(session)
    logger.info("contractors_consolidated", **result)
    return result
