"""Job bpm.scan (specs/bpm.md): arrenca i avança instàncies cada hora."""

from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.db import session_factory
from app.jobs.registry import JobContext, job
from app.modules.bpm import service
from app.modules.bpm.models import BpmInstance, BpmInstanceStatus, BpmWorkflow

logger = structlog.get_logger()


@job("bpm.scan")
async def bpm_scan(ctx: JobContext) -> dict[str, Any]:
    from app.core import modules as module_flags

    if "bpm" in await module_flags.disabled_modules():
        return {"skipped": "module-disabled"}

    started = 0
    truncated = False
    advanced = 0
    finished = 0
    cancelled = 0

    async with session_factory() as session:
        workflows = list(
            (
                await session.execute(
                    select(BpmWorkflow)
                    .options(selectinload(BpmWorkflow.steps))
                    .where(BpmWorkflow.active.is_(True))
                )
            ).scalars()
        )
        for workflow in workflows:
            contract_ids = await service.contracts_matching_trigger(session, workflow)
            if len(contract_ids) > service.MAX_STARTS_PER_SCAN:
                truncated = True
                contract_ids = contract_ids[: service.MAX_STARTS_PER_SCAN]
                logger.warning(
                    "bpm_scan_truncated",
                    workflow_id=workflow.id,
                    limit=service.MAX_STARTS_PER_SCAN,
                )
            for contract_id in contract_ids:
                if await service.start_instance(session, workflow, contract_id) is not None:
                    started += 1

        running = list(
            (
                await session.execute(
                    select(BpmInstance).where(BpmInstance.status == BpmInstanceStatus.RUNNING)
                )
            ).scalars()
        )
        for instance in running:
            outcome = await service.advance_instance(session, instance)
            if outcome == "advanced":
                advanced += 1
            elif outcome == "done":
                finished += 1
            elif outcome == "cancelled":
                cancelled += 1

        await session.commit()

    result = {
        "started": started,
        "advanced": advanced,
        "done": finished,
        "cancelled": cancelled,
        "truncated": truncated,
    }
    logger.info("bpm_scan_finished", **result)
    return result
