"""Job webhooks.dispatch (specs/outbound-webhooks.md)."""

from typing import Any

import structlog

from app.core.db import session_factory
from app.jobs.registry import JobContext, job
from app.modules.webhooks.service import publish_outbox, send_due_deliveries

logger = structlog.get_logger()


@job("webhooks.dispatch")
async def dispatch_webhooks(ctx: JobContext) -> dict[str, Any]:
    async with session_factory() as session:
        published = await publish_outbox(session)
        counters = await send_due_deliveries(session)
        await session.commit()
    result = {"published": published, **counters}
    logger.info("webhooks_dispatched", **result)
    return result
