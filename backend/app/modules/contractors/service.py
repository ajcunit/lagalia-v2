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
)


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

    # 2) Reutilització per NIF (primer registrat = canònic candidat).
    if tax_id:
        existing = (
            await session.execute(
                select(Contractor)
                .where(Contractor.tax_id == tax_id)
                .order_by(Contractor.id.asc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if existing is not None:
            if name and name != existing.canonical_name:
                # Nom nou per al mateix NIF: contractor propi; els duplicats
                # per NIF es detecten a cada sync (defecte v1 corregit).
                created = Contractor(canonical_name=name, tax_id=tax_id, nationality=nationality)
                session.add(created)
                await session.flush()
                return ResolvedContractor(contractor_id=created.id, raw_name=name)
            return ResolvedContractor(contractor_id=existing.id, raw_name=name)

    contractor = Contractor(
        canonical_name=name or f"(sense nom, NIF {tax_id})",
        tax_id=tax_id,
        nationality=nationality,
    )
    session.add(contractor)
    await session.flush()
    return ResolvedContractor(contractor_id=contractor.id, raw_name=name)


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
