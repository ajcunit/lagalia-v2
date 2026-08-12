"""Jobs enrich.contract i enrich.batch (specs/pscp-enrichment.md)."""

from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import session_factory
from app.core.storage import get_storage, safe_name
from app.integrations import hub
from app.integrations.base import ConnectorError
from app.integrations.models import SyncKind, SyncStatus, SyncTrigger
from app.integrations.pscp import extract
from app.integrations.pscp.connector import PscpClient, PscpConnector
from app.integrations.socrata import sync_common as sc
from app.jobs.registry import JobContext, job
from app.modules.contracts.models import (
    AwardCriterion,
    CommitteeMember,
    Contract,
    ContractPhase,
    PhaseDocument,
)

logger = structlog.get_logger()

_PROMOTED = (
    "is_harmonized",
    "allows_extensions",
    "allows_modifications",
    "social_reserve",
    "received_offers",
)


async def _pscp_connector() -> PscpConnector:
    async with session_factory() as session:
        connector = await hub.get_connector(session, "pscp")
        await session.commit()
    if not isinstance(connector, PscpConnector):
        raise TypeError("El hub ha resolt un connector inesperat per a 'pscp'")
    return connector


async def _enrich_one(
    session: AsyncSession,
    client: PscpClient,
    contract: Contract,
    *,
    download_documents: bool,
) -> dict[str, Any]:
    phase_urls: dict[str, str] = contract.phase_urls or {}
    enrichment: dict[str, Any] = {}
    criteria: list[dict[str, Any]] = []
    committee: list[dict[str, str | None]] = []
    documents: list[dict[str, Any]] = []

    seen_criteria: set[str] = set()
    seen_members: set[tuple[str | None, str | None]] = set()
    skipped_phases: list[str] = []
    for phase_name, url in phase_urls.items():
        if not url:
            continue
        try:
            payload = await client.fetch_phase(str(url))
        except ConnectorError as exc:
            # Expedients antics amb enllaços caducats a la font: es continua
            # amb les fases que responguin (spec pscp-enrichment).
            skipped_phases.append(phase_name)
            logger.warning(
                "pscp_phase_skipped", contract_id=contract.id, phase=phase_name, error=str(exc)
            )
            continue
        enrichment[phase_name] = extract.extract_scalars(phase_name, payload)
        # El mateix criteri/membre pot aparèixer a més d'una fase: es dedueix.
        for criterion in extract.collect_criteria(payload):
            if criterion["name"] not in seen_criteria:
                seen_criteria.add(criterion["name"])
                criterion["position"] = len(criteria) + 1
                criteria.append(criterion)
        for member in extract.collect_committee(payload):
            member_key = (member["first_name"], member["last_name"])
            if member_key not in seen_members:
                seen_members.add(member_key)
                committee.append(member)
        for document in extract.collect_documents(payload, client.base_url):
            document["phase"] = phase_name
            documents.append(document)

    if not enrichment and skipped_phases:
        raise ConnectorError(
            f"cap fase disponible a la font (totes caducades: {', '.join(skipped_phases)})"
        )

    # Escalars promocionats (l'última fase que en tingui, guanya).
    for scalars in enrichment.values():
        for field in _PROMOTED:
            if field in scalars:
                setattr(contract, field, scalars[field])

    contract.enrichment = enrichment
    contract.enriched_at = datetime.now(UTC)

    # Idempotent: es reconstrueixen criteris i mesa.
    await session.execute(delete(AwardCriterion).where(AwardCriterion.contract_id == contract.id))
    await session.execute(delete(CommitteeMember).where(CommitteeMember.contract_id == contract.id))
    for criterion in criteria:
        session.add(AwardCriterion(contract_id=contract.id, **criterion))
    for member in committee:
        session.add(CommitteeMember(contract_id=contract.id, **member))

    storage = get_storage() if download_documents else None
    stored = 0
    for document in documents:
        existing = (
            await session.execute(
                select(PhaseDocument).where(
                    PhaseDocument.contract_id == contract.id,
                    PhaseDocument.source_doc_id == document["source_doc_id"],
                )
            )
        ).scalar_one_or_none()
        row = existing or PhaseDocument(
            contract_id=contract.id,
            source_doc_id=document["source_doc_id"],
            phase=ContractPhase(document["phase"]),
        )
        row.title = document["title"]
        row.doc_type = document["doc_type"]
        row.download_url = document["download_url"]
        if row.size is None:
            row.size = document.get("size")
        if storage is not None and not row.storage_key:
            try:
                content, content_type = await client.download_document(document["download_url"])
                key = (
                    f"contracts/{contract.id}/{document['phase']}/"
                    f"{document['source_doc_id']}-{safe_name(document['title'])}"
                )
                await storage.put(key, content, content_type)
                row.storage_key = key
                row.size = len(content)
                stored += 1
            except ConnectorError as exc:
                logger.warning(
                    "pscp_document_skipped",
                    contract_id=contract.id,
                    doc=document["source_doc_id"],
                    error=str(exc),
                )
        if existing is None:
            session.add(row)

    await session.flush()
    return {
        "phases": len(enrichment),
        "skipped_phases": skipped_phases,
        "criteria": len(criteria),
        "committee": len(committee),
        "documents": len(documents),
        "stored": stored,
    }


@job("enrich.contract")
async def enrich_contract(ctx: JobContext) -> dict[str, Any]:
    payload = ctx.payload or {}
    contract_id = int(payload["contract_id"])
    force = bool(payload.get("force", False))
    download_documents = bool(payload.get("download_documents", True))

    connector = await _pscp_connector()
    async with session_factory() as session:
        contract = await session.get(Contract, contract_id)
        if contract is None:
            raise RuntimeError(f"contracte {contract_id} inexistent")
        if contract.enriched_at is not None and not force:
            return {"skipped": True}
        if not contract.phase_urls:
            return {"skipped": True, "reason": "sense phase_urls"}
        async with connector.client() as client:
            result = await _enrich_one(
                session, client, contract, download_documents=download_documents
            )
        await session.commit()
    logger.info("enrich_contract_finished", contract_id=contract_id, **result)
    return result


@job("enrich.batch")
async def enrich_batch(ctx: JobContext) -> dict[str, Any]:
    payload = ctx.payload or {}
    force = bool(payload.get("force", False))
    download_documents = bool(payload.get("download_documents", True))
    limit = payload.get("limit")

    run_id = await sc.create_run(SyncKind.ENRICHMENT, SyncTrigger(payload.get("trigger", "manual")))
    counters = {"new": 0, "updated": 0, "unchanged": 0, "failed": 0}

    connector = await _pscp_connector()
    async with session_factory() as session:
        stmt = select(Contract.id).where(Contract.phase_urls.is_not(None))
        if not force:
            stmt = stmt.where(Contract.enriched_at.is_(None))
        if limit:
            stmt = stmt.limit(int(limit))
        contract_ids = list((await session.execute(stmt)).scalars())

    try:
        async with connector.client() as client:
            for index, contract_id in enumerate(contract_ids, start=1):
                async with session_factory() as session:
                    contract = await session.get(Contract, contract_id)
                    if contract is None:
                        continue
                    try:
                        already = contract.enriched_at is not None
                        await _enrich_one(
                            session, client, contract, download_documents=download_documents
                        )
                        await session.commit()
                        counters["updated" if already else "new"] += 1
                    except Exception as exc:
                        await session.rollback()
                        counters["failed"] += 1
                        await sc.log_item(
                            run_id, contract.file_code, "error", f"{type(exc).__name__}: {exc}"
                        )
                if index % 5 == 0 or index == len(contract_ids):
                    await ctx.set_progress(
                        min(99, (index * 100) // max(1, len(contract_ids))),
                        f"{index}/{len(contract_ids)} expedients enriquits",
                    )
    except Exception as exc:
        await sc.fail_run(run_id, exc)
        raise

    status = SyncStatus.PARTIAL if counters["failed"] else SyncStatus.SUCCESS
    await sc.finish_run(
        run_id,
        status=status,
        counters=counters,
        total_source=len(contract_ids),
        endpoint=connector.config["base_url"],
    )
    logger.info("enrich_batch_finished", run_id=run_id, **counters)
    return {"sync_run_id": run_id, **counters}
