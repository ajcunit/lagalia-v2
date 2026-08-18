"""Job sync.cpv: diccionari CPV amb jerarquia de 4 nivells per fila.

Desviació d'A1 §9 anotada a specs/remaining-syncs.md: el dataset real
porta la jerarquia completa a cada fila; el pare es deriva d'allà.
"""

from typing import Any

import structlog
from sqlalchemy import select

from app.core.db import session_factory
from app.integrations import hub
from app.integrations.models import SyncKind, SyncStatus, SyncTrigger
from app.integrations.socrata import sync_common as sc
from app.integrations.socrata.connector import SocrataConnector
from app.integrations.socrata.query import SoqlQuery
from app.jobs.registry import JobContext, job
from app.modules.contracts.models import CpvCode, CpvLevel

logger = structlog.get_logger()

# (camp codi, camp descripció, nivell, camp codi del pare)
_LEVELS = (
    ("cpv_divisi", "descripci_divisi", CpvLevel.DIVISION, None),
    ("cpv_grup", "descripci_grup", CpvLevel.GROUP, "cpv_divisi"),
    ("cpv_classe", "descripci_classe", CpvLevel.CLASS, "cpv_grup"),
    ("cpv_categoria", "descripci_categoria", CpvLevel.CATEGORY, "cpv_classe"),
)


def levels_from_row(record: dict[str, Any]) -> list[dict[str, Any]]:
    """Els 4 nivells (codi, descripció, nivell, pare) d'una fila del dataset."""
    levels = []
    for code_field, description_field, level, parent_field in _LEVELS:
        code = str(record.get(code_field) or "").strip()
        description = str(record.get(description_field) or "").strip()
        if not code or not description:
            continue
        parent = str(record.get(parent_field) or "").strip() if parent_field else None
        levels.append(
            {
                "code": code,
                "description": description,
                "level": level,
                "parent_code": parent or None,
            }
        )
    return levels


@job("sync.cpv", max_attempts=3, backoff_seconds=120)
async def sync_cpv(ctx: JobContext) -> dict[str, Any]:
    payload = ctx.payload or {}
    trigger = SyncTrigger(payload.get("trigger", "manual"))
    run_id = await sc.create_run(SyncKind.CPV, trigger)
    counters = {"new": 0, "updated": 0, "unchanged": 0, "failed": 0}
    total_rows = 0

    try:
        async with session_factory() as session:
            connector = await hub.get_connector(session, "socrata")
            await session.commit()
        if not isinstance(connector, SocrataConnector):
            raise TypeError("El hub ha resolt un connector inesperat per a 'socrata'")

        # Dedupe en memòria: cada divisió/grup apareix a milers de files.
        codes: dict[str, dict[str, Any]] = {}
        query = SoqlQuery(connector.config["dataset_cpv"]).order_by("cpv_categoria")
        async with connector.client() as client:
            async for record in client.iter_records(query, page_size=5000):
                total_rows += 1
                for entry in levels_from_row(record):
                    codes[entry["code"]] = entry

        await ctx.set_progress(50, f"{len(codes)} codis únics de {total_rows} files")

        items = list(codes.values())
        for start in range(0, len(items), 500):
            async with session_factory() as session:
                for entry in items[start : start + 500]:
                    existing = (
                        await session.execute(select(CpvCode).where(CpvCode.code == entry["code"]))
                    ).scalar_one_or_none()
                    if existing is None:
                        session.add(CpvCode(**entry))
                        counters["new"] += 1
                    elif (
                        existing.description != entry["description"]
                        or existing.parent_code != entry["parent_code"]
                        or existing.level != entry["level"]
                    ):
                        existing.description = entry["description"]
                        existing.parent_code = entry["parent_code"]
                        existing.level = entry["level"]
                        counters["updated"] += 1
                    else:
                        counters["unchanged"] += 1
                await session.commit()
            await ctx.set_progress(
                min(99, 50 + ((start + 500) * 50) // max(1, len(items))),
                f"{min(start + 500, len(items))}/{len(items)} codis",
            )
    except Exception as exc:
        await sc.fail_run(run_id, exc)
        raise

    await sc.finish_run(
        run_id,
        status=SyncStatus.SUCCESS,
        counters=counters,
        total_source=total_rows,
        endpoint=f"{connector.config['base_url']}/resource/{connector.config['dataset_cpv']}.json",
    )
    logger.info("sync_cpv_finished", run_id=run_id, **counters)
    return {"sync_run_id": run_id, **counters}
