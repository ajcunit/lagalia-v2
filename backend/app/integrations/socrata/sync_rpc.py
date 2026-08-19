"""Jobs sync.extensions i sync.minor_contracts (dataset RPC hb6v-jcbf).

Esquema real i regles: specs/remaining-syncs.md.
"""

from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import session_factory
from app.integrations import hub
from app.integrations.models import SyncKind, SyncStatus, SyncTrigger
from app.integrations.socrata import sync_common as sc
from app.integrations.socrata.connector import SocrataConnector
from app.integrations.socrata.query import SoqlQuery
from app.jobs.registry import JobContext, job
from app.modules.contractors.service import resolve_contractor
from app.modules.contracts.models import (
    ChangeType,
    Contract,
    ContractHistoryEntry,
    Extension,
    Modification,
)
from app.modules.minor_contracts.models import MinorContract

logger = structlog.get_logger()

_PAGE_SIZE = 1000

# Camps mapejables del dataset RPC (registre únic; specs/field-mapping.md).
# Els defaults transcriuen specs/remaining-syncs.md; overrides a field_mappings.
from app.integrations.socrata.mapping import FieldDef  # noqa: E402

RPC_FIELDS: dict[str, FieldDef] = {
    "minor.contract_type": FieldDef("tipus_contracte", "text", "Menor: tipus de contracte"),
    "minor.description": FieldDef("contracte", "text", "Menor: descripció"),
    "minor.award_amount": FieldDef("import_adjudicacio", "amount", "Menor: import adjudicació"),
    "minor.award_date": FieldDef("data_adjudicacio", "date", "Menor: data adjudicació"),
    "minor.fiscal_year": FieldDef("exercici", "int", "Menor: exercici"),
    "minor.duration_years": FieldDef("anys_durada", "int", "Menor: durada (anys)"),
    "minor.duration_months": FieldDef("mesos_durada", "int", "Menor: durada (mesos)"),
    "minor.duration_days": FieldDef("dies_durada", "int", "Menor: durada (dies)"),
    "minor.settlement_type": FieldDef("tipus_liquidacio", "text", "Menor: tipus de liquidació"),
    "minor.settlement_date": FieldDef("data_liquidacio", "date", "Menor: data de liquidació"),
    "minor.settlement_amount": FieldDef(
        "import_liquidacio", "amount", "Menor: import de liquidació"
    ),
    "minor.contractor_name": FieldDef("adjudicatari", "text", "Menor: adjudicatari"),
    "extension.number": FieldDef("numero_prorroga", "int", "Pròrroga: número"),
    "extension.start_date": FieldDef("data_inici_prorroga", "date", "Pròrroga: inici"),
    "extension.end_date": FieldDef("data_fi_prorroga", "date", "Pròrroga: fi"),
    "extension.amount": FieldDef("import_adjudicacio", "amount", "Pròrroga: import"),
    "extension.fiscal_year": FieldDef("exercici", "int", "Pròrroga: exercici"),
    "modification.approved_at": FieldDef("data_adjudicacio", "date", "Modificació: aprovada"),
    "modification.type": FieldDef("situaci_contractual", "text", "Modificació: tipus"),
    "modification.amount": FieldDef("import_adjudicacio", "amount", "Modificació: import"),
}


def _src(overrides: dict[str, str] | None, target: str) -> str:
    return (overrides or {}).get(target) or RPC_FIELDS[target].source


async def _rpc_connector() -> SocrataConnector:
    async with session_factory() as session:
        connector = await hub.get_connector(session, "socrata")
        await session.commit()
    if not isinstance(connector, SocrataConnector):
        raise TypeError("El hub ha resolt un connector inesperat per a 'socrata'")
    return connector


async def _fetch_rpc_rows(
    connector: SocrataConnector, ine10: str, *, only_minor: bool = False
) -> list[dict[str, Any]]:
    query = SoqlQuery(connector.config["dataset_rpc"]).where_eq("id_organisme_contractant", ine10)
    if only_minor:
        query = query.where_eq("procediment_adjudicacio", "Menor")
    query = query.order_by("codi_expedient")
    rows: list[dict[str, Any]] = []
    async with connector.client() as client:
        async for record in client.iter_records(query, page_size=_PAGE_SIZE):
            rows.append(record)
    return rows


# ─────────────────────────── pròrrogues i modificacions ───────────────────────────


async def _expedient_contracts(session: AsyncSession, file_code: str) -> list[Contract]:
    result = await session.execute(
        select(Contract).where(Contract.file_code == file_code).order_by(Contract.id.asc())
    )
    return list(result.scalars())


async def _propagate_end_date(
    session: AsyncSession, contracts: list[Contract], new_end: Any
) -> None:
    """La pròrroga sobreescriu la data de fi de tot l'expedient (02 §2.8)."""
    if new_end is None:
        return
    for row in contracts:
        if row.calculated_end_date is None or new_end > row.calculated_end_date:
            session.add(
                ContractHistoryEntry(
                    contract_id=row.id,
                    field="calculated_end_date",
                    old_value=str(row.calculated_end_date) if row.calculated_end_date else None,
                    new_value=str(new_end),
                    change_type=ChangeType.SYNC,
                )
            )
            row.calculated_end_date = new_end


def extension_values(
    record: dict[str, Any], overrides: dict[str, str] | None = None
) -> dict[str, Any]:
    return {
        "start_date": sc.parse_date_value(record.get(_src(overrides, "extension.start_date"))),
        "end_date": sc.parse_date_value(record.get(_src(overrides, "extension.end_date"))),
        "amount": sc.parse_amount(record.get(_src(overrides, "extension.amount"))),
        "fiscal_year": sc.parse_int(record.get(_src(overrides, "extension.fiscal_year"))),
    }


async def _upsert_extension(
    session: AsyncSession,
    record: dict[str, Any],
    run_id: int,
    overrides: dict[str, str] | None = None,
) -> str:
    file_code = str(record.get("codi_expedient") or "").strip()
    if not file_code:
        raise ValueError("pròrroga sense codi_expedient")

    contracts = await _expedient_contracts(session, file_code)
    if not contracts:
        await sc.log_item(run_id, file_code, "unmatched", "expedient sense contracte local")
        return "unmatched"

    representative = contracts[0]
    number = sc.parse_int(record.get(_src(overrides, "extension.number"))) or 1
    values = extension_values(record, overrides)

    existing = (
        await session.execute(
            select(Extension).where(
                Extension.contract_id == representative.id, Extension.number == number
            )
        )
    ).scalar_one_or_none()

    if existing is not None:
        unchanged = all(getattr(existing, k) == v for k, v in values.items())
        if unchanged:
            return "unchanged"
        for key, value in values.items():
            setattr(existing, key, value)
        existing.raw = record
        outcome = "updated"
    else:
        session.add(Extension(contract_id=representative.id, number=number, raw=record, **values))
        outcome = "new"

    await _propagate_end_date(session, contracts, values["end_date"])
    await session.flush()
    return outcome


def modification_values(
    record: dict[str, Any], overrides: dict[str, str] | None = None
) -> dict[str, Any]:
    return {
        "approved_at": sc.parse_date_value(record.get(_src(overrides, "modification.approved_at"))),
        "type": str(record.get(_src(overrides, "modification.type")) or "")[:100] or None,
        "amount": sc.parse_amount(record.get(_src(overrides, "modification.amount"))),
    }


async def _upsert_modification(
    session: AsyncSession,
    record: dict[str, Any],
    run_id: int,
    overrides: dict[str, str] | None = None,
) -> str:
    file_code = str(record.get("codi_expedient") or "").strip()
    if not file_code:
        raise ValueError("modificació sense codi_expedient")

    contracts = await _expedient_contracts(session, file_code)
    if not contracts:
        await sc.log_item(run_id, file_code, "unmatched", "expedient sense contracte local")
        return "unmatched"

    representative = contracts[0]
    existing_count = (
        await session.execute(
            select(Modification).where(Modification.contract_id == representative.id)
        )
    ).scalars()
    numbers = [m.number for m in existing_count]
    number = sc.parse_int(record.get(_src(overrides, "extension.number"))) or (
        max(numbers, default=0) + 1
    )
    if number in numbers:
        return "unchanged"

    # Cap mostra real de modificació al dataset de Cunit: mapeig mínim amb
    # raw complet (specs/remaining-syncs.md), revisable quan n'hi hagi.
    session.add(
        Modification(
            contract_id=representative.id,
            number=number,
            raw=record,
            **modification_values(record, overrides),
        )
    )
    await session.flush()
    return "new"


@job("sync.extensions", max_attempts=3, backoff_seconds=120)
async def sync_extensions(ctx: JobContext) -> dict[str, Any]:
    payload = ctx.payload or {}
    trigger = SyncTrigger(payload.get("trigger", "manual"))
    ine10 = await sc.required_ine10()
    run_id = await sc.create_run(SyncKind.EXTENSIONS, trigger, job_id=ctx.job_id)
    counters = {"new": 0, "updated": 0, "unchanged": 0, "unmatched": 0, "failed": 0}
    rows: list[dict[str, Any]] = []

    try:
        from app.integrations.field_mappings import get_overrides

        async with session_factory() as session:
            overrides = await get_overrides(session, "rpc")
        connector = await _rpc_connector()
        rows = await _fetch_rpc_rows(connector, ine10)
        relevant = [
            (sc.classify_situacio(r.get("situaci_contractual")), r)
            for r in rows
            if sc.classify_situacio(r.get("situaci_contractual")) in ("extension", "modification")
        ]
        await ctx.set_progress(10, f"{len(relevant)} pròrrogues/modificacions de {len(rows)}")

        for kind, record in relevant:
            async with session_factory() as session:
                try:
                    if kind == "extension":
                        outcome = await _upsert_extension(session, record, run_id, overrides)
                    else:
                        outcome = await _upsert_modification(session, record, run_id, overrides)
                    await session.commit()
                    counters[outcome] += 1
                except Exception as exc:
                    await session.rollback()
                    counters["failed"] += 1
                    await sc.log_item(
                        run_id,
                        str(record.get("codi_expedient", "")),
                        "error",
                        f"{type(exc).__name__}: {exc}",
                    )
    except Exception as exc:
        await sc.fail_run(run_id, exc)
        raise

    status = SyncStatus.PARTIAL if counters["failed"] else SyncStatus.SUCCESS
    await sc.finish_run(
        run_id,
        status=status,
        counters=counters,
        total_source=len(rows),
        endpoint=f"{connector.config['base_url']}/resource/{connector.config['dataset_rpc']}.json",
        error_summary={"unmatched": counters["unmatched"]} if counters["unmatched"] else None,
    )
    logger.info("sync_extensions_finished", run_id=run_id, **counters)
    return {"sync_run_id": run_id, **counters}


# ─────────────────────────────── contractes menors ───────────────────────────────

_MINOR_FIELDS = (
    "contract_type",
    "description",
    "award_amount",
    "award_date",
    "fiscal_year",
    "duration_years",
    "duration_months",
    "duration_days",
    "settlement_type",
    "settlement_date",
    "settlement_amount",
)


def merge_minor_records(
    file_code: str,
    group: list[dict[str, Any]],
    overrides: dict[str, str] | None = None,
) -> dict[str, Any] | None:
    """Fusió adjudicació + liquidació d'un expedient (02 §2.5)."""
    award = next(
        (r for r in group if sc.classify_situacio(r.get("situaci_contractual")) == "minor_award"),
        None,
    )
    settlement = next(
        (r for r in group if sc.classify_situacio(r.get("situaci_contractual")) == "settlement"),
        None,
    )
    if award is None and settlement is None:
        return None
    base = award or settlement or {}

    def src(target: str) -> str:
        return _src(overrides, target)

    description = base.get(src("minor.description")) or base.get("descripcio_expedient")
    return {
        "file_code": file_code,
        "contract_type": str(base.get(src("minor.contract_type")) or "")[:100] or None,
        "description": str(description or "") or None,
        "award_amount": sc.parse_amount((award or {}).get(src("minor.award_amount"))),
        "award_date": sc.parse_date_value((award or {}).get(src("minor.award_date"))),
        "fiscal_year": sc.parse_int(base.get(src("minor.fiscal_year"))),
        "duration_years": sc.parse_int(base.get(src("minor.duration_years"))),
        "duration_months": sc.parse_int(base.get(src("minor.duration_months"))),
        "duration_days": sc.parse_int(base.get(src("minor.duration_days"))),
        "settlement_type": str((settlement or {}).get(src("minor.settlement_type")) or "")[:100]
        or None,
        "settlement_date": sc.parse_date_value(
            (settlement or {}).get(src("minor.settlement_date"))
        ),
        "settlement_amount": sc.parse_amount(
            (settlement or {}).get(src("minor.settlement_amount"))
        ),
        "raw_award": award,
        "raw_settlement": settlement,
        "_contractor_name": str(base.get(src("minor.contractor_name")) or "").strip() or None,
    }


async def _upsert_minor(session: AsyncSession, values: dict[str, Any]) -> str:
    contractor_name = values.pop("_contractor_name")
    existing = (
        await session.execute(
            select(MinorContract).where(MinorContract.file_code == values["file_code"])
        )
    ).scalar_one_or_none()
    now = datetime.now(UTC)

    if existing is not None:
        unchanged = all(getattr(existing, k) == values.get(k) for k in _MINOR_FIELDS)
        if unchanged:
            existing.last_synced_at = now
            return "unchanged"
        for key, value in values.items():
            setattr(existing, key, value)
        existing.last_synced_at = now
        await session.flush()
        return "updated"

    # El dataset RPC no té NIF: resolució només per nom/àlies (spec).
    resolved = await resolve_contractor(session, name=contractor_name, tax_id=None)
    minor = MinorContract(
        **values,
        contractor_id=resolved.contractor_id if resolved else None,
        last_synced_at=now,
    )
    session.add(minor)
    await session.flush()
    return "new"


@job("sync.minor_contracts", max_attempts=3, backoff_seconds=120)
async def sync_minor_contracts(ctx: JobContext) -> dict[str, Any]:
    payload = ctx.payload or {}
    trigger = SyncTrigger(payload.get("trigger", "manual"))
    ine10 = await sc.required_ine10()
    run_id = await sc.create_run(SyncKind.MINOR, trigger, job_id=ctx.job_id)
    counters = {"new": 0, "updated": 0, "unchanged": 0, "failed": 0}
    rows: list[dict[str, Any]] = []

    try:
        from app.integrations.field_mappings import get_overrides

        async with session_factory() as session:
            overrides = await get_overrides(session, "rpc")
        connector = await _rpc_connector()
        rows = await _fetch_rpc_rows(connector, ine10, only_minor=True)
        groups: dict[str, list[dict[str, Any]]] = {}
        for record in rows:
            file_code = str(record.get("codi_expedient") or "").strip()
            if file_code:
                groups.setdefault(file_code, []).append(record)
        await ctx.set_progress(10, f"{len(groups)} expedients menors ({len(rows)} registres)")

        for index, (file_code, group) in enumerate(groups.items(), start=1):
            values = merge_minor_records(file_code, group, overrides)
            if values is None:
                continue
            async with session_factory() as session:
                try:
                    outcome = await _upsert_minor(session, values)
                    await session.commit()
                    counters[outcome] += 1
                except Exception as exc:
                    await session.rollback()
                    counters["failed"] += 1
                    await sc.log_item(run_id, file_code, "error", f"{type(exc).__name__}: {exc}")
            if index % 500 == 0:
                await ctx.set_progress(
                    min(99, 10 + (index * 80) // max(1, len(groups))),
                    f"{index}/{len(groups)} expedients",
                )
    except Exception as exc:
        await sc.fail_run(run_id, exc)
        raise

    status = SyncStatus.PARTIAL if counters["failed"] else SyncStatus.SUCCESS
    await sc.finish_run(
        run_id,
        status=status,
        counters=counters,
        total_source=len(rows),
        endpoint=f"{connector.config['base_url']}/resource/{connector.config['dataset_rpc']}.json",
    )
    logger.info("sync_minor_finished", run_id=run_id, **counters)
    return {"sync_run_id": run_id, **counters}
