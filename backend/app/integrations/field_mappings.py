"""Overrides manuals de mapeig font → model (specs/field-mapping.md).

Els defaults viuen a `socrata/mapping.py` (annex A1); aquí només es
persisteixen i serveixen les correccions manuals, i el job de re-mapatge
local que les aplica al `raw` ja guardat sense cap crida externa.
"""

from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import session_factory
from app.integrations.socrata import mapping
from app.jobs.registry import JobContext, job

logger = structlog.get_logger()

# Camps que el remap actualitza (mapejables + calculats que en depenen).
# Mai la identitat (file_code/status/lot) ni el contractista.
REMAP_FIELDS = tuple(mapping.MAPPABLE_FIELDS) + (
    "start_date",
    "end_date",
    "calculated_end_date",
    "duration_months",
)


async def get_overrides(session: AsyncSession, source: str) -> dict[str, str]:
    rows = (
        await session.execute(
            text("SELECT target_field, source_field FROM field_mappings WHERE source = :s"),
            {"s": source},
        )
    ).all()
    return {row.target_field: row.source_field for row in rows}


@job("sync.remap_contracts")
async def remap_contracts(ctx: JobContext) -> dict[str, Any]:
    """Re-aplica el mapeig vigent sobre el raw guardat de cada contracte.

    Cap crida externa: tot surt de `contracts.raw`. Historifica els canvis
    com fa el sync (change_type='sync').
    """
    from app.modules.contracts.models import ChangeType, Contract, ContractHistoryEntry

    async with session_factory() as session:
        overrides = await get_overrides(session, "socrata")
        ids = [
            row.id
            for row in (
                await session.execute(
                    text("SELECT id FROM contracts WHERE raw IS NOT NULL ORDER BY id")
                )
            ).all()
        ]

    updated = 0
    unchanged = 0
    failed = 0
    for index, contract_id in enumerate(ids):
        async with session_factory() as session:
            try:
                contract = await session.get(Contract, contract_id)
                if contract is None or not contract.raw:
                    continue
                values = mapping.map_contract(dict(contract.raw), overrides)
                changed = False
                for field in REMAP_FIELDS:
                    old, new = getattr(contract, field), values.get(field)
                    if old != new:
                        changed = True
                        session.add(
                            ContractHistoryEntry(
                                contract_id=contract.id,
                                field=field,
                                old_value=None if old is None else str(old),
                                new_value=None if new is None else str(new),
                                change_type=ChangeType.SYNC,
                            )
                        )
                        setattr(contract, field, new)
                if changed:
                    updated += 1
                else:
                    unchanged += 1
                await session.commit()
            except Exception as exc:  # una fila corrupta no atura el remap
                await session.rollback()
                failed += 1
                logger.warning("remap_failed", contract_id=contract_id, error=str(exc))
        if (index + 1) % 500 == 0:
            await ctx.set_progress(
                min(99, int((index + 1) * 100 / max(1, len(ids)))),
                f"{index + 1}/{len(ids)} contractes re-mapejats",
            )

    logger.info(
        "remap_contracts_finished", total=len(ids), updated=updated, failed=failed
    )
    return {"total": len(ids), "updated": updated, "unchanged": unchanged, "failed": failed}
