"""Job sync.contracts: pipeline de referència (08-hub-integracions.md §4).

Idempotent (dedup_key al job), incremental per data_actualitzacio,
amb sync_run + comptadors, historial per camp i errors per registre.
"""

from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import session_factory
from app.integrations import hub
from app.integrations.models import (
    SyncItemLog,
    SyncKind,
    SyncRun,
    SyncStatus,
    SyncTrigger,
)
from app.integrations.socrata import mapping
from app.integrations.socrata.connector import SocrataConnector
from app.integrations.socrata.query import SoqlQuery
from app.jobs.registry import JobContext, job
from app.modules.config.models import Setting
from app.modules.contractors.service import detect_tax_id_duplicates, resolve_contractor
from app.modules.contracts.models import (
    ChangeType,
    Contract,
    ContractHistoryEntry,
    contract_departments,
)
from app.modules.contracts.repository import manually_edited_fields
from app.modules.contracts.rules import first_matching_department, load_active_rules

logger = structlog.get_logger()

_PAGE_SIZE = 1000

# Camps que es comparen i historifiquen quan el hash canvia.
_TRACKED_FIELDS = (
    "status",
    "subject",
    "contract_type",
    "procedure",
    "processing_type",
    "awarding_body",
    "awarding_department",
    "tender_amount",
    "award_amount",
    "award_amount_vat",
    "estimated_value",
    "budget_no_vat",
    "budget_vat",
    "published_at",
    "updated_at_source",
    "formalized_at",
    "start_date",
    "end_date",
    "calculated_end_date",
    "duration_months",
    "cpv_code",
    "cpv_description",
    "financing",
)


async def _ine10(session: AsyncSession) -> str:
    setting = (
        await session.execute(select(Setting).where(Setting.key == "org.ine10_code"))
    ).scalar_one_or_none()
    if setting is None or not setting.value:
        raise RuntimeError(
            "org.ine10_code no configurat: cal el codi INE10 de l'ens (setup) "
            "per filtrar el dataset"
        )
    return str(setting.value)


async def _last_success_started_at(session: AsyncSession) -> datetime | None:
    return (
        await session.execute(
            select(SyncRun.started_at)
            .where(SyncRun.kind == SyncKind.CONTRACTS, SyncRun.status == SyncStatus.SUCCESS)
            .order_by(SyncRun.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def _inherit_departments(session: AsyncSession, file_code: str) -> list[int]:
    """Departaments d'altres files del mateix expedient (herència)."""
    result = await session.execute(
        select(contract_departments.c.department_id)
        .join(Contract, Contract.id == contract_departments.c.contract_id)
        .where(Contract.file_code == file_code)
        .distinct()
    )
    return [row[0] for row in result]


async def _assign_department(session: AsyncSession, contract_id: int, department_id: int) -> None:
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    await session.execute(
        pg_insert(contract_departments)
        .values(contract_id=contract_id, department_id=department_id)
        .on_conflict_do_nothing()
    )


async def _upsert_record(
    session: AsyncSession,
    record: dict[str, Any],
    rules: list[Any],
    overrides: dict[str, str] | None = None,
) -> str:
    """Processa un registre; retorna 'new' | 'updated' | 'unchanged'."""
    values = mapping.map_contract(record, overrides)
    if not values["file_code"]:
        raise ValueError("registre sense codi_expedient")
    now = datetime.now(UTC)

    # Identitat primària: id_intern de la font (estable per lot). El portal
    # SUBSTITUEIX la fila quan la fase avança (p. ex. Adjudicació →
    # Formalització): si es busca per (expedient, estat, lot) el canvi de
    # fase sembla una fila nova i la vella queda òrfena (cas 4732/2026).
    existing = None
    id_intern = str(record.get("id_intern") or "").strip()
    if id_intern:
        existing = (
            await session.execute(
                select(Contract)
                .where(
                    Contract.file_code == values["file_code"],
                    Contract.lot == values["lot"],
                    Contract.raw["id_intern"].astext == id_intern,
                )
                .order_by(Contract.id)
                .limit(1)
            )
        ).scalar_one_or_none()
    if existing is None:
        existing = (
            await session.execute(
                select(Contract).where(
                    Contract.file_code == values["file_code"],
                    Contract.status == values["status"],
                    Contract.lot == values["lot"],
                )
            )
        ).scalar_one_or_none()

    if existing is not None and existing.content_hash == values["content_hash"]:
        existing.last_synced_at = now
        return "unchanged"

    contractor = await resolve_contractor(session, **mapping.contractor_fields(record, overrides))
    if contractor is not None:
        values["contractor_id"] = contractor.contractor_id
        values["raw_contractor_name"] = contractor.raw_name

    if existing is not None:
        # Els camps esmenats a mà queden protegits: el manual mana sobre
        # la font (specs/contracts-api.md, esmenes de dades PSCP).
        pinned = await manually_edited_fields(session, existing.id)
        # Actualització camp a camp amb historial `sync` (A1 §7).
        for field in _TRACKED_FIELDS:
            if field in pinned:
                continue
            old, new = getattr(existing, field), values.get(field)
            if old != new:
                session.add(
                    ContractHistoryEntry(
                        contract_id=existing.id,
                        field=field,
                        old_value=None if old is None else str(old),
                        new_value=None if new is None else str(new),
                        change_type=ChangeType.SYNC,
                    )
                )
        for field, value in values.items():
            if field in pinned:
                continue
            setattr(existing, field, value)
        existing.last_synced_at = now
        await session.flush()
        return "updated"

    contract = Contract(**values, first_synced_at=now, last_synced_at=now)
    session.add(contract)
    await session.flush()

    # Nous: herència de departaments del mateix expedient → regles.
    inherited = await _inherit_departments(session, contract.file_code)
    for department_id in inherited:
        await _assign_department(session, contract.id, department_id)
    if not inherited:
        matched_department = first_matching_department(rules, values)
        if matched_department is not None:
            await _assign_department(session, contract.id, matched_department)
    return "new"


@job("sync.contracts", max_attempts=3, backoff_seconds=120)
async def sync_contracts(ctx: JobContext) -> dict[str, Any]:
    payload = ctx.payload or {}
    trigger = SyncTrigger(payload.get("trigger", "manual"))
    full = bool(payload.get("full", False))

    async with session_factory() as session:
        ine10 = await _ine10(session)
        last_success = None if full else await _last_success_started_at(session)
        run = SyncRun(kind=SyncKind.CONTRACTS, trigger=trigger, started_at=datetime.now(UTC))
        session.add(run)
        await session.commit()
        run_id = run.id

    counters = {"new": 0, "updated": 0, "unchanged": 0, "failed": 0}
    status = SyncStatus.SUCCESS
    endpoint = None
    processed = 0
    duplicates = 0

    try:
        async with session_factory() as session:
            connector = await hub.get_connector(session, "socrata")
            await session.commit()
        if not isinstance(connector, SocrataConnector):  # defensa de registre
            raise TypeError("El hub ha resolt un connector inesperat per a 'socrata'")

        query = SoqlQuery(connector.config["dataset_contracts"]).where_ine10("codi_ine10", ine10)
        # Incremental només si el dataset ho permet (08 §2.1): camp configurable.
        incremental_field = connector.config.get("incremental_field")
        if last_success is not None and incremental_field:
            query = query.where_gte_timestamp(
                str(incremental_field), last_success.replace(tzinfo=None)
            )
        query = query.order_by("codi_expedient")
        endpoint = f"{connector.config['base_url']}/resource/{query.dataset_id}.json"

        async with connector.client() as client:
            async with session_factory() as session:
                rules = await load_active_rules(session)
                # Overrides manuals de mapeig, un cop per execució.
                from app.integrations.field_mappings import get_overrides

                overrides = await get_overrides(session, "socrata")
                await session.commit()

            async for record in client.iter_records(query, page_size=_PAGE_SIZE):
                processed += 1
                async with session_factory() as session:
                    try:
                        outcome = await _upsert_record(session, record, rules, overrides)
                        await session.commit()
                        counters[outcome] += 1
                    except Exception as exc:
                        await session.rollback()
                        counters["failed"] += 1
                        status = SyncStatus.PARTIAL
                        async with session_factory() as log_session:
                            log_session.add(
                                SyncItemLog(
                                    sync_run_id=run_id,
                                    file_code=str(record.get("codi_expedient", ""))[:100],
                                    outcome="error",
                                    message=f"{type(exc).__name__}: {exc}"[:1000],
                                )
                            )
                            await log_session.commit()
                if processed % _PAGE_SIZE == 0:
                    # Total desconegut per endavant: progrés fitat al 99%.
                    await ctx.set_progress(
                        min(99, (processed // _PAGE_SIZE) * 10),
                        f"{processed} registres processats",
                    )

        # Postprocés: duplicats d'adjudicatari per NIF, SEMPRE (defecte v1).
        async with session_factory() as session:
            duplicates = await detect_tax_id_duplicates(session)
            await session.commit()

    except Exception as exc:
        async with session_factory() as session:
            failed_run = await session.get(SyncRun, run_id)
            if failed_run is not None:
                failed_run.status = SyncStatus.FAILED
                failed_run.finished_at = datetime.now(UTC)
                failed_run.error_summary = {"error": f"{type(exc).__name__}: {exc}"}
                await session.commit()
        raise

    async with session_factory() as session:
        finished_run = await session.get(SyncRun, run_id)
        if finished_run is not None:
            finished_run.status = status
            finished_run.finished_at = datetime.now(UTC)
            finished_run.new_count = counters["new"]
            finished_run.updated_count = counters["updated"]
            finished_run.unchanged_count = counters["unchanged"]
            finished_run.total_source = processed
            finished_run.endpoint = endpoint
            if counters["failed"]:
                finished_run.error_summary = {"failed_items": counters["failed"]}
            await session.commit()

    logger.info("sync_contracts_finished", run_id=run_id, **counters)
    return {"sync_run_id": run_id, **counters, "contractor_duplicates": duplicates}
