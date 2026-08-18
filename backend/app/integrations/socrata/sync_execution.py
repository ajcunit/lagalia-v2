"""Job sync.execution: publicacions de la fase d'execució (specs/execution-sync.md).

Dataset 8idu-wkjv (B-017): actuacions d'execució per expedient/lot. Dedup
per hash del registre font; vincle al contracte local per file_code (fila
representativa), refet a cada sincronització.
"""

from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import session_factory
from app.integrations import hub
from app.integrations.models import SyncKind, SyncStatus, SyncTrigger
from app.integrations.socrata import sync_common as sc
from app.integrations.socrata.connector import SocrataConnector
from app.integrations.socrata.mapping import FieldDef, content_hash
from app.integrations.socrata.query import SoqlQuery
from app.jobs.registry import JobContext, job

logger = structlog.get_logger()

_PAGE_SIZE = 1000

# Camps mapejables del dataset d'execució (font `execution` al mapejador).
EXECUTION_FIELDS: dict[str, FieldDef] = {
    "execution.lot": FieldDef("numero_lot", "text", "Execució: lot"),
    "execution.action_type": FieldDef(
        "tipus_actuacio_execucio", "text", "Execució: tipus d'actuació"
    ),
    "execution.action_name": FieldDef(
        "denominacio_actuacio", "text", "Execució: denominació"
    ),
    "execution.date": FieldDef("data", "date", "Execució: data"),
    "execution.end_date": FieldDef("data_fi", "date", "Execució: data fi"),
    "execution.amount": FieldDef("import_sense_iva", "amount", "Execució: import (sense IVA)"),
    "execution.contractor_name": FieldDef("denominacio", "text", "Execució: adjudicatari"),
    "execution.contractor_tax_id": FieldDef(
        "identificacio", "text", "Execució: adjudicatari (NIF)"
    ),
    "execution.observations": FieldDef("observacions", "text", "Execució: observacions"),
    "execution.url_json": FieldDef("url_json", "text", "Execució: URL JSON de detall"),
}


def _src(overrides: dict[str, str] | None, target: str) -> str:
    return (overrides or {}).get(target) or EXECUTION_FIELDS[target].source


# Grups de documents del JSON de detall d'una actuació (observats al portal,
# per tipus: modificacions, pròrrogues i genèrics d'«altres actuacions»).
DOC_GROUPS = (
    "informeJustificatiu",
    "resolucioModificacio",
    "formalitzacioModificacio",
    "alegacions",
    "altraDocumentacio",
    "resolucioProrroga",
    "formalitzacioProrroga",
    "resolucioExtincio",
    "resolucio",
)

_LANG_KEYS = {"ca", "es", "en", "oc"}


def extract_execution_detail(detail: Any, base_url: str) -> dict[str, Any]:
    """Del JSON de detall (`url_json`): supòsit habilitant + documents per grup.

    Els documents tenen la mateixa forma que els de fase ({id, titol, hash,
    mida}) agrupats per tipus i idioma; el supòsit habilitant és un catàleg
    multiidioma ca→es→en.
    """
    from app.integrations.pscp.extract import DOWNLOAD_PATH, ml

    documents: list[dict[str, Any]] = []
    seen: set[str] = set()
    suposit: str | None = None

    def visit(node: Any, group: str | None) -> None:
        nonlocal suposit
        if isinstance(node, dict):
            if suposit is None and "supositHabilitant" in node:
                suposit = ml(node.get("supositHabilitant"))
            if (
                group is not None
                and isinstance(node.get("id"), int)
                and isinstance(node.get("titol"), str)
                and isinstance(node.get("hash"), str)
            ):
                source_doc_id = str(node["id"])
                if source_doc_id not in seen:
                    seen.add(source_doc_id)
                    size = str(node.get("mida", ""))
                    documents.append(
                        {
                            "source_doc_id": source_doc_id,
                            "group": group,
                            "title": node["titol"][:500],
                            "size": int(size) if size.isdigit() else None,
                            "download_url": base_url
                            + DOWNLOAD_PATH.format(id=node["id"], hash=node["hash"]),
                        }
                    )
                return
            for key, value in node.items():
                next_group = group
                if key in DOC_GROUPS:
                    next_group = key
                elif key in _LANG_KEYS:
                    pass  # l'idioma no canvia el grup
                elif isinstance(value, (dict, list)) and group is None:
                    next_group = None
                visit(value, next_group)
        elif isinstance(node, list):
            for value in node:
                visit(value, group)

    visit(detail, None)
    return {"suposit_habilitant": suposit, "documents": documents}


def _url_value(value: Any) -> str | None:
    if isinstance(value, dict):
        url = value.get("url")
        return str(url) if url else None
    return str(value) if value else None


def execution_values(
    record: dict[str, Any], overrides: dict[str, str] | None = None
) -> dict[str, Any]:
    """Valors de columna de `contract_executions` (sense el vincle)."""

    def src(target: str) -> str:
        return _src(overrides, target)

    return {
        "file_code": str(record.get("codi_expedient") or "").strip(),
        "lot": str(record.get(src("execution.lot")) or "").strip()[:50] or None,
        "action_type": str(record.get(src("execution.action_type")) or "").strip()[:200]
        or None,
        "action_name": str(record.get(src("execution.action_name")) or "").strip() or None,
        "date": sc.parse_date_value(record.get(src("execution.date"))),
        "end_date": sc.parse_date_value(record.get(src("execution.end_date"))),
        "amount": sc.parse_amount(record.get(src("execution.amount"))),
        "contractor_name": str(record.get(src("execution.contractor_name")) or "").strip()[
            :500
        ]
        or None,
        "contractor_tax_id": str(
            record.get(src("execution.contractor_tax_id")) or ""
        ).strip()[:50]
        or None,
        "observations": str(record.get(src("execution.observations")) or "").strip() or None,
        "url_json": _url_value(record.get(src("execution.url_json"))),
    }


async def _representative_contract_id(session: AsyncSession, file_code: str) -> int | None:
    row = (
        await session.execute(
            text("SELECT id FROM contracts WHERE file_code = :f ORDER BY id LIMIT 1"),
            {"f": file_code},
        )
    ).first()
    return row.id if row else None


async def _upsert_execution(
    session: AsyncSession, record: dict[str, Any], overrides: dict[str, str] | None
) -> str:
    values = execution_values(record, overrides)
    if not values["file_code"]:
        raise ValueError("registre d'execució sense codi_expedient")
    record_hash = content_hash(record)
    contract_id = await _representative_contract_id(session, values["file_code"])

    existing = (
        await session.execute(
            text("SELECT id, contract_id FROM contract_executions WHERE content_hash = :h"),
            {"h": record_hash},
        )
    ).first()
    if existing is not None:
        # El vincle es refà (l'expedient pot haver arribat després).
        await session.execute(
            text(
                "UPDATE contract_executions SET contract_id = :c, last_synced_at = :n "
                "WHERE id = :i"
            ),
            {"c": contract_id, "n": datetime.now(UTC), "i": existing.id},
        )
        return "unchanged" if existing.contract_id == contract_id else "updated"

    import json as _json

    await session.execute(
        text(
            "INSERT INTO contract_executions (contract_id, file_code, lot, action_type, "
            "action_name, date, end_date, amount, contractor_name, contractor_tax_id, "
            "observations, url_json, raw, content_hash) "
            "VALUES (:contract_id, :file_code, :lot, :action_type, :action_name, :date, "
            ":end_date, :amount, :contractor_name, :contractor_tax_id, :observations, "
            ":url_json, CAST(:raw AS jsonb), :content_hash)"
        ),
        {
            **values,
            "contract_id": contract_id,
            "raw": _json.dumps(record, default=str),
            "content_hash": record_hash,
        },
    )
    return "new" if contract_id is not None else "unmatched"


@job("sync.execution")
async def sync_execution(ctx: JobContext) -> dict[str, Any]:
    payload = ctx.payload or {}
    trigger = SyncTrigger(payload.get("trigger", "manual"))
    ine10 = await sc.required_ine10()
    run_id = await sc.create_run(SyncKind.EXECUTION, trigger)
    counters = {"new": 0, "updated": 0, "unchanged": 0, "unmatched": 0, "failed": 0}
    processed = 0
    endpoint = None

    try:
        from app.integrations.field_mappings import get_overrides

        async with session_factory() as session:
            overrides = await get_overrides(session, "execution")
            connector = await hub.get_connector(session, "socrata")
            await session.commit()
        if not isinstance(connector, SocrataConnector):
            raise TypeError("El hub ha resolt un connector inesperat per a 'socrata'")

        dataset = connector.config["dataset_execution"]
        query = (
            SoqlQuery(dataset).where_ine10("codi_ine10", ine10).order_by("codi_expedient")
        )
        endpoint = f"{connector.config['base_url']}/resource/{dataset}.json"

        async with connector.client() as client:
            async for record in client.iter_records(query, page_size=_PAGE_SIZE):
                processed += 1
                async with session_factory() as session:
                    try:
                        outcome = await _upsert_execution(session, record, overrides)
                        await session.commit()
                        counters[outcome] += 1
                    except Exception as exc:
                        await session.rollback()
                        counters["failed"] += 1
                        await sc.log_item(
                            run_id,
                            str(record.get("codi_expedient", ""))[:100],
                            "error",
                            f"{type(exc).__name__}: {exc}",
                        )
                if processed % _PAGE_SIZE == 0:
                    await ctx.set_progress(
                        min(99, (processed // _PAGE_SIZE) * 20),
                        f"{processed} actuacions processades",
                    )
    except Exception as exc:
        await sc.fail_run(run_id, exc)
        raise

    # Enriquiment del detall (supòsit habilitant + documents) via connector
    # pscp per a les files que encara no el tenen (o totes amb force_detail).
    detail_counters = await _enrich_details(force=bool(payload.get("force_detail", False)))
    counters["detail_fetched"] = detail_counters["fetched"]
    counters["detail_failed"] = detail_counters["failed"]

    status = SyncStatus.PARTIAL if counters["failed"] else SyncStatus.SUCCESS
    await sc.finish_run(
        run_id,
        status=status,
        counters={k: counters[k] for k in ("new", "updated", "unchanged", "failed")},
        total_source=processed,
        endpoint=endpoint,
        error_summary={"unmatched": counters["unmatched"]} if counters["unmatched"] else None,
    )
    logger.info("sync_execution_finished", run_id=run_id, **counters)
    return {"sync_run_id": run_id, **counters}


async def _enrich_details(force: bool = False) -> dict[str, int]:
    """Descarrega el JSON de detall de cada actuació (validat pel connector
    pscp, mateixa whitelist de host que les fases) i en persisteix el supòsit
    habilitant i els documents. Els errors per fila no aturen res."""
    from app.integrations.pscp.connector import PscpConnector

    async with session_factory() as session:
        condition = "" if force else "AND detail_fetched_at IS NULL"
        rows = (
            await session.execute(
                text(
                    "SELECT id, url_json, contract_id FROM contract_executions "  # noqa: S608
                    f"WHERE url_json IS NOT NULL {condition} ORDER BY id"
                )
            )
        ).all()
    if not rows:
        return {"fetched": 0, "failed": 0}

    async with session_factory() as session:
        connector = await hub.get_connector(session, "pscp")
        await session.commit()
    if not isinstance(connector, PscpConnector):
        raise TypeError("El hub ha resolt un connector inesperat per a 'pscp'")

    import json as _json

    fetched = 0
    failed = 0
    async with connector.client() as client:
        for row in rows:
            try:
                detail = await client.fetch_phase(str(row.url_json))
                extracted = extract_execution_detail(detail, client.base_url)
                async with session_factory() as session:
                    await session.execute(
                        text(
                            "UPDATE contract_executions SET suposit_habilitant = :s, "
                            "documents = CAST(:d AS jsonb), detail_fetched_at = now() "
                            "WHERE id = :i"
                        ),
                        {
                            "s": extracted["suposit_habilitant"],
                            "d": _json.dumps(extracted["documents"]),
                            "i": row.id,
                        },
                    )
                    # Els documents d'execució són documents de fase de ple
                    # dret (fase «execucio»): entren a la tria del RAG, la
                    # revisió legal i el xat per document.
                    if row.contract_id is not None:
                        await _upsert_phase_documents(
                            session, client, row.contract_id, extracted["documents"]
                        )
                    await session.commit()
                fetched += 1
            except Exception as exc:  # una fila amb detall caducat no atura res
                failed += 1
                logger.warning(
                    "execution_detail_failed", execution_id=row.id, error=str(exc)
                )
    logger.info("execution_details_enriched", fetched=fetched, failed=failed)
    return {"fetched": fetched, "failed": failed}


async def _upsert_phase_documents(
    session: AsyncSession, client: Any, contract_id: int, documents: list[dict[str, Any]]
) -> None:
    """Upsert dels documents d'una actuació com a phase_documents (execucio).

    Si la fase «execucio» és a `rag.indexable_phases` (o no hi ha restricció),
    se'n descarrega còpia local perquè el RAG els pugui indexar.
    """
    from app.core.storage import safe_name
    from app.integrations.pscp.enrich import _indexable_phases

    indexable = await _indexable_phases(session)
    download = indexable is None or "execucio" in indexable
    for document in documents:
        existing = (
            await session.execute(
                text(
                    "SELECT id, storage_key FROM phase_documents "
                    "WHERE contract_id = :c AND source_doc_id = :s"
                ),
                {"c": contract_id, "s": document["source_doc_id"]},
            )
        ).first()
        if existing is None:
            document_id = (
                await session.execute(
                    text(
                        "INSERT INTO phase_documents (contract_id, phase, source_doc_id, "
                        "title, doc_type, size, download_url) "
                        "VALUES (:c, 'execucio', :s, :t, :dt, :sz, :u) RETURNING id"
                    ),
                    {
                        "c": contract_id,
                        "s": document["source_doc_id"],
                        "t": document["title"],
                        "dt": str(document.get("group") or "")[:100] or None,
                        "sz": document.get("size"),
                        "u": document["download_url"],
                    },
                )
            ).scalar_one()
            storage_key = None
        else:
            document_id, storage_key = existing.id, existing.storage_key
        if download and not storage_key:
            try:
                content, content_type = await client.download_document(
                    document["download_url"]
                )
                from app.core.storage import get_storage

                key = (
                    f"contracts/{contract_id}/execucio/"
                    f"{document['source_doc_id']}-{safe_name(document['title'])}"
                )
                await get_storage().put(key, content, content_type)
                await session.execute(
                    text(
                        "UPDATE phase_documents SET storage_key = :k, size = :sz "
                        "WHERE id = :i"
                    ),
                    {"k": key, "sz": len(content), "i": document_id},
                )
            except Exception as exc:  # un document caducat no atura res
                logger.warning(
                    "execution_document_skipped",
                    contract_id=contract_id,
                    doc=document["source_doc_id"],
                    error=str(exc),
                )


@job("sync.remap_execution")
async def remap_execution(ctx: JobContext) -> dict[str, Any]:
    """Re-aplica el mapeig `execution` al raw guardat (cap crida externa)."""
    from app.integrations.field_mappings import get_overrides

    async with session_factory() as session:
        overrides = await get_overrides(session, "execution")
        ids = [
            row.id
            for row in (
                await session.execute(text("SELECT id FROM contract_executions ORDER BY id"))
            ).all()
        ]

    updated = 0
    failed = 0
    fields = (
        "lot", "action_type", "action_name", "date", "end_date", "amount",
        "contractor_name", "contractor_tax_id", "observations", "url_json",
    )
    for row_id in ids:
        async with session_factory() as session:
            try:
                row = (
                    await session.execute(
                        text("SELECT raw FROM contract_executions WHERE id = :i"),
                        {"i": row_id},
                    )
                ).first()
                if row is None or not row.raw:
                    continue
                values = execution_values(dict(row.raw), overrides)
                assignments = ", ".join(f"{field} = :{field}" for field in fields)
                result = await session.execute(
                    text(
                        f"UPDATE contract_executions SET {assignments} "  # noqa: S608 — camps fixos
                        "WHERE id = :i AND (" +
                        " OR ".join(f"{f} IS DISTINCT FROM :{f}" for f in fields) + ")"
                    ),
                    {**{f: values[f] for f in fields}, "i": row_id},
                )
                if result.rowcount:
                    updated += 1
                await session.commit()
            except Exception as exc:
                await session.rollback()
                failed += 1
                logger.warning("remap_execution_failed", id=row_id, error=str(exc))
    await ctx.set_progress(100, "re-mapatge d'execucions completat")
    logger.info("remap_execution_finished", total=len(ids), updated=updated, failed=failed)
    return {"total": len(ids), "updated": updated, "failed": failed}
