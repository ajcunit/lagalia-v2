"""Resolució d'adjudicataris a la ingesta i detecció de duplicats per NIF.

A1 §6: l'àlies substitueix el nom abans de desar; el nom original es
conserva a raw_contractor_name (traçabilitat, millora v2).
"""

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.contractors.models import (
    Contractor,
    ContractorAlias,
    ContractorDuplicate,
    ContractorDuplicateStatus,
)
from app.modules.contractors.normalize import identity_key


@dataclass(frozen=True)
class ResolvedContractor:
    contractor_id: int
    raw_name: str | None


async def resolve_contractor(
    session: AsyncSession,
    *,
    name: str | None,
    tax_id: str | None,
    nationality: str | None = None,
) -> ResolvedContractor | None:
    """Resol (o crea) l'adjudicatari d'un registre de la font."""
    if not name and not tax_id:
        return None

    # 1) Àlies exacte → canònic.
    if name:
        alias = (
            await session.execute(select(ContractorAlias).where(ContractorAlias.alias == name))
        ).scalar_one_or_none()
        if alias is not None:
            return ResolvedContractor(contractor_id=alias.contractor_id, raw_name=name)

    # 2) Reutilització per NIF.
    if tax_id:
        candidates = list(
            (
                await session.execute(
                    select(Contractor)
                    .where(Contractor.tax_id == tax_id)
                    .order_by(Contractor.id.asc())
                )
            ).scalars()
        )
        if candidates:
            if not name or any(name == c.canonical_name for c in candidates):
                matched = next(
                    (c for c in candidates if name and name == c.canonical_name), candidates[0]
                )
                return ResolvedContractor(contractor_id=matched.id, raw_name=name)

            # Variant trivial (mateixa identitat normalitzada) → àlies del
            # contractor existent, mai un contractor nou (B-011).
            normalized = identity_key(name)
            for candidate in candidates:
                if normalized and normalized == identity_key(candidate.canonical_name):
                    session.add(ContractorAlias(alias=name, contractor_id=candidate.id))
                    await session.flush()
                    return ResolvedContractor(contractor_id=candidate.id, raw_name=name)

            # Nom genuïnament diferent: contractor propi; el parell de
            # duplicat es detecta a cada sync (defecte v1 corregit).
            created = Contractor(canonical_name=name, tax_id=tax_id, nationality=nationality)
            session.add(created)
            await session.flush()
            return ResolvedContractor(contractor_id=created.id, raw_name=name)

    contractor = Contractor(
        canonical_name=name or f"(sense nom, NIF {tax_id})",
        tax_id=tax_id,
        nationality=nationality,
    )
    session.add(contractor)
    await session.flush()
    return ResolvedContractor(contractor_id=contractor.id, raw_name=name)


async def merge_contractors(session: AsyncSession, *, winner_id: int, loser_id: int) -> None:
    """Fusiona el perdedor dins del guanyador: refs, àlies i eliminació.

    El nom del perdedor esdevé àlies del guanyador perquè les ingestes
    futures resolguin soles.
    """
    from sqlalchemy import delete, update

    from app.modules.contracts.models import Contract
    from app.modules.minor_contracts.models import MinorContract

    loser = await session.get(Contractor, loser_id)
    winner = await session.get(Contractor, winner_id)
    if loser is None or winner is None:
        raise ValueError("contractor inexistent en la fusió")

    await session.execute(
        update(Contract).where(Contract.contractor_id == loser_id).values(contractor_id=winner_id)
    )
    await session.execute(
        update(MinorContract)
        .where(MinorContract.contractor_id == loser_id)
        .values(contractor_id=winner_id)
    )
    await session.execute(
        update(ContractorAlias)
        .where(ContractorAlias.contractor_id == loser_id)
        .values(contractor_id=winner_id)
    )
    if loser.canonical_name != winner.canonical_name:
        existing_alias = (
            await session.execute(
                select(ContractorAlias).where(ContractorAlias.alias == loser.canonical_name)
            )
        ).scalar_one_or_none()
        if existing_alias is None:
            session.add(ContractorAlias(alias=loser.canonical_name, contractor_id=winner_id))

    # Altres parells pendents del perdedor: es descarten (la propera
    # detecció els regenerarà contra el guanyador si encara toca).
    await session.execute(
        delete(ContractorDuplicate).where(
            ContractorDuplicate.status == ContractorDuplicateStatus.PENDING,
            (ContractorDuplicate.contractor_id_1 == loser_id)
            | (ContractorDuplicate.contractor_id_2 == loser_id),
        )
    )
    await session.delete(loser)
    await session.flush()


async def _linked_counts(session: AsyncSession, contractor_ids: list[int]) -> dict[int, int]:
    """Contractes (majors + menors) vinculats per contractor."""
    from app.modules.contracts.models import Contract
    from app.modules.minor_contracts.models import MinorContract

    counts = dict.fromkeys(contractor_ids, 0)
    for model in (Contract, MinorContract):
        rows = (
            await session.execute(
                select(model.contractor_id, func.count())
                .where(model.contractor_id.in_(contractor_ids))
                .group_by(model.contractor_id)
            )
        ).all()
        for contractor_id, count in rows:
            counts[contractor_id] = counts.get(contractor_id, 0) + count
    return counts


async def consolidate_same_identity(session: AsyncSession) -> dict[str, int]:
    """Fusió automàtica de variants trivials del mateix NIF (B-011).

    Regla determinista: mateixa identitat normalitzada = mateixa empresa.
    El guanyador és el membre amb més contractes vinculats.
    """
    duplicated_tax_ids = (
        select(Contractor.tax_id)
        .where(Contractor.tax_id.is_not(None))
        .group_by(Contractor.tax_id)
        .having(func.count() > 1)
    )
    rows = (
        await session.execute(
            select(Contractor.id, Contractor.tax_id, Contractor.canonical_name)
            .where(Contractor.tax_id.in_(duplicated_tax_ids))
            .order_by(Contractor.id.asc())
        )
    ).all()

    groups: dict[str, dict[str, list[tuple[int, str]]]] = {}
    for contractor_id, tax_id, canonical_name in rows:
        clusters = groups.setdefault(tax_id, {})
        clusters.setdefault(identity_key(canonical_name), []).append(
            (contractor_id, canonical_name)
        )

    merged = 0
    clusters_touched = 0
    for clusters in groups.values():
        for members in clusters.values():
            if len(members) < 2:
                continue
            clusters_touched += 1
            member_ids = [m[0] for m in members]
            counts = await _linked_counts(session, member_ids)
            winner_id = max(member_ids, key=lambda cid: (counts.get(cid, 0), -cid))
            for loser_id in member_ids:
                if loser_id != winner_id:
                    await merge_contractors(session, winner_id=winner_id, loser_id=loser_id)
                    merged += 1

    regenerated = await detect_tax_id_duplicates(session)
    return {"clusters": clusters_touched, "merged": merged, "pairs_after": regenerated}


async def resolve_duplicate_group(
    session: AsyncSession, *, tax_id: str, action: str, canonical_id: int | None
) -> dict[str, int]:
    """Fusió en bloc de tot el grup d'un NIF, o rebuig de tots els parells."""
    members = list(
        (
            await session.execute(
                select(Contractor.id).where(Contractor.tax_id == tax_id).order_by(Contractor.id)
            )
        ).scalars()
    )
    if len(members) < 2:
        return {"merged": 0, "rejected": 0}

    if action == "merge":
        if canonical_id is None or canonical_id not in members:
            raise ValueError("canonical_id ha de ser un membre del grup")
        merged = 0
        for loser_id in members:
            if loser_id != canonical_id:
                await merge_contractors(session, winner_id=canonical_id, loser_id=loser_id)
                merged += 1
        return {"merged": merged, "rejected": 0}

    # reject: tots els parells pendents entre membres del grup.
    from sqlalchemy import update

    result = await session.execute(
        update(ContractorDuplicate)
        .where(
            ContractorDuplicate.status == ContractorDuplicateStatus.PENDING,
            ContractorDuplicate.contractor_id_1.in_(members),
            ContractorDuplicate.contractor_id_2.in_(members),
        )
        .values(status=ContractorDuplicateStatus.REJECTED, resolved_at=func.now())
    )
    await session.flush()
    return {"merged": 0, "rejected": int(getattr(result, "rowcount", 0) or 0)}


async def detect_tax_id_duplicates(session: AsyncSession) -> int:
    """(Re)genera parells pendents de contractors amb el mateix NIF.

    S'executa a cada sync (A1/08 §4); els parells ja resolts no es toquen.
    """
    duplicated_tax_ids = (
        select(Contractor.tax_id)
        .where(Contractor.tax_id.is_not(None))
        .group_by(Contractor.tax_id)
        .having(func.count() > 1)
    )
    rows = (
        await session.execute(
            select(Contractor.id, Contractor.tax_id)
            .where(Contractor.tax_id.in_(duplicated_tax_ids))
            .order_by(Contractor.id.asc())
        )
    ).all()

    by_tax_id: dict[str, list[int]] = {}
    for contractor_id, tax_id in rows:
        by_tax_id.setdefault(tax_id, []).append(contractor_id)

    created = 0
    for ids in by_tax_id.values():
        for i, first in enumerate(ids):
            for second in ids[i + 1 :]:
                result = await session.execute(
                    pg_insert(ContractorDuplicate)
                    .values(contractor_id_1=first, contractor_id_2=second)
                    .on_conflict_do_nothing(constraint="uq_contractor_duplicates_pair")
                )
                created += int(getattr(result, "rowcount", 0) or 0)
    await session.flush()
    return created
