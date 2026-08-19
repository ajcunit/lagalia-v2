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
                # Les pròrrogues manen sobre la fi calculada (02 §2.8): el
                # remap re-aplica la propagació per no trepitjar-les.
                extension_end = (
                    await session.execute(
                        text(
                            "SELECT max(e.end_date) FROM extensions e "
                            "JOIN contracts c ON c.id = e.contract_id "
                            "WHERE c.file_code = :f"
                        ),
                        {"f": contract.file_code},
                    )
                ).scalar_one_or_none()
                if extension_end is not None and (
                    values.get("calculated_end_date") is None
                    or extension_end > values["calculated_end_date"]
                ):
                    values["calculated_end_date"] = extension_end
                # El manual mana: els camps esmenats a mà no es remapegen.
                from app.modules.contracts.repository import manually_edited_fields

                pinned = await manually_edited_fields(session, contract.id)
                changed = False
                for field in REMAP_FIELDS:
                    if field in pinned:
                        continue
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

    logger.info("remap_contracts_finished", total=len(ids), updated=updated, failed=failed)
    return {"total": len(ids), "updated": updated, "unchanged": unchanged, "failed": failed}


@job("sync.remap_rpc")
async def remap_rpc(ctx: JobContext) -> dict[str, Any]:
    """Re-aplica el mapeig RPC al raw guardat de menors, pròrrogues i
    modificacions. Cap crida externa."""
    from app.integrations.socrata.sync_rpc import (
        _MINOR_FIELDS,
        extension_values,
        merge_minor_records,
        modification_values,
    )
    from app.modules.contracts.models import Extension, Modification
    from app.modules.minor_contracts.models import MinorContract

    async with session_factory() as session:
        overrides = await get_overrides(session, "rpc")

    counters = {"minors": 0, "extensions": 0, "modifications": 0, "failed": 0}

    async with session_factory() as session:
        minor_ids = [
            row.id
            for row in (
                await session.execute(
                    text(
                        "SELECT id FROM minor_contracts "
                        "WHERE raw_award IS NOT NULL OR raw_settlement IS NOT NULL"
                    )
                )
            ).all()
        ]
    for minor_id in minor_ids:
        async with session_factory() as session:
            try:
                minor = await session.get(MinorContract, minor_id)
                if minor is None:
                    continue
                group = [r for r in (minor.raw_award, minor.raw_settlement) if r]
                values = merge_minor_records(minor.file_code, [dict(r) for r in group], overrides)
                if values is None:
                    continue
                changed = False
                for field in _MINOR_FIELDS:
                    if getattr(minor, field) != values.get(field):
                        setattr(minor, field, values.get(field))
                        changed = True
                if changed:
                    counters["minors"] += 1
                await session.commit()
            except Exception as exc:
                await session.rollback()
                counters["failed"] += 1
                logger.warning("remap_minor_failed", minor_id=minor_id, error=str(exc))

    async with session_factory() as session:
        try:
            extensions = (
                await session.execute(text("SELECT id FROM extensions WHERE raw IS NOT NULL"))
            ).all()
            for row in extensions:
                extension = await session.get(Extension, row.id)
                if extension is None or not extension.raw:
                    continue
                values = extension_values(dict(extension.raw), overrides)
                if any(getattr(extension, k) != v for k, v in values.items()):
                    for key, value in values.items():
                        setattr(extension, key, value)
                    counters["extensions"] += 1
            modifications = (
                await session.execute(text("SELECT id FROM modifications WHERE raw IS NOT NULL"))
            ).all()
            for row in modifications:
                modification = await session.get(Modification, row.id)
                if modification is None or not modification.raw:
                    continue
                values = modification_values(dict(modification.raw), overrides)
                if any(getattr(modification, k) != v for k, v in values.items()):
                    for key, value in values.items():
                        setattr(modification, key, value)
                    counters["modifications"] += 1
            await session.commit()
        except Exception as exc:
            await session.rollback()
            counters["failed"] += 1
            logger.warning("remap_rpc_failed", error=str(exc))

    await ctx.set_progress(100, "re-mapatge RPC completat")
    logger.info("remap_rpc_finished", **counters)
    return counters
