"""Motor de la migració v1→v2 (specs/v1-migration.md).

Idempotent: tot són conciliacions per clau estable (nom de departament,
email, NIF, clau natural de contracte). Una sola transacció de destí:
--dry-run = rollback final.
"""

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.crypto import encrypt_value
from app.core.db import session_factory
from app.migration import source_map
from app.modules.audit.models import AuditActorType
from app.modules.audit.service import record_audit
from app.modules.contractors.models import Contractor, ContractorAlias
from app.modules.contracts.models import Contract, ContractSource, InternalStatus
from app.modules.departments.models import Department
from app.modules.minor_contracts.models import MinorContract
from app.modules.users.models import User, UserRole

logger = structlog.get_logger()


@dataclass
class EntityResult:
    read: int = 0
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    orphans: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "read": self.read,
            "created": self.created,
            "updated": self.updated,
            "unchanged": self.unchanged,
            "orphans": self.orphans,
        }


def _slug(value: str, max_length: int = 40) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]+", "-", normalized).strip("-").upper()[:max_length] or "DEPT"


async def _read_source(source_dsn: str, schema: str) -> dict[str, list[dict[str, Any]]]:
    """Llegeix la v1 sencera en memòria (volum municipal), en només lectura."""
    engine = create_async_engine(source_dsn, poolclass=NullPool)
    data: dict[str, list[dict[str, Any]]] = {}
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SET TRANSACTION READ ONLY"))
            for entity in source_map.SELECTS:
                rows = (await conn.execute(text(source_map.select_sql(entity, schema)))).mappings()
                data[entity] = [dict(r) for r in rows]
    finally:
        await engine.dispose()
    return data


async def _migrate_departments(
    session: AsyncSession, rows: list[dict[str, Any]]
) -> tuple[EntityResult, dict[int, int]]:
    result = EntityResult(read=len(rows))
    id_map: dict[int, int] = {}
    existing = {
        name.strip().casefold(): dept_id
        for dept_id, name in (await session.execute(select(Department.id, Department.name))).all()
    }
    for row in rows:
        name = (row["nombre"] or "").strip()
        if not name:
            result.orphans.append(f"departament v1 id={row['id']} sense nom")
            continue
        key = name.casefold()
        if key in existing:
            id_map[row["id"]] = existing[key]
            result.unchanged += 1
            continue
        department = Department(code=f"V1-{_slug(name)}", name=name)
        session.add(department)
        await session.flush()
        existing[key] = department.id
        id_map[row["id"]] = department.id
        result.created += 1
    return result, id_map


async def _migrate_users(
    session: AsyncSession,
    rows: list[dict[str, Any]],
    memberships: list[dict[str, Any]],
    department_map: dict[int, int],
) -> tuple[EntityResult, dict[int, int]]:
    result = EntityResult(read=len(rows))
    id_map: dict[int, int] = {}
    for row in rows:
        email = (row["email"] or "").strip().lower()
        if not email:
            result.orphans.append(f"usuari v1 id={row['id']} sense email")
            continue
        role_value = source_map.ROLE_MAP.get(row["rol"])
        if role_value is None:
            result.orphans.append(f"usuari {email}: rol v1 desconegut {row['rol']!r}")
            continue
        user = (
            await session.execute(select(User).where(func.lower(User.email) == email))
        ).scalar_one_or_none()
        dni_encrypted = encrypt_value(row["dni"].strip()) if row.get("dni") else None
        if user is None:
            user = User(
                name=row["nombre"] or email,
                email=email,
                role=UserRole(role_value),
                active=bool(row["activo"]),
                can_audit=bool(row["permiso_auditoria"]),
                can_plan=bool(row["permiso_pla_contractacio"]),
                dni_encrypted=dni_encrypted,
                password_hash=None,  # KDF v1 incompatible: restabliment de contrasenya
            )
            session.add(user)
            await session.flush()
            result.created += 1
        else:
            before = (user.role.value, user.can_audit, user.can_plan, user.active)
            user.role = UserRole(role_value)
            user.can_audit = bool(row["permiso_auditoria"])
            user.can_plan = bool(row["permiso_pla_contractacio"])
            user.active = bool(row["activo"])
            if dni_encrypted is not None and user.dni_encrypted is None:
                user.dni_encrypted = dni_encrypted
            after = (user.role.value, user.can_audit, user.can_plan, user.active)
            if before == after:
                result.unchanged += 1
            else:
                result.updated += 1
        id_map[row["id"]] = user.id

    # Pertinences usuari↔departament (afegeix les que faltin).
    for membership in memberships:
        user_id = id_map.get(membership["usuario_id"])
        department_id = department_map.get(membership["departamento_id"])
        if user_id is None or department_id is None:
            continue
        await session.execute(
            text(
                "INSERT INTO user_departments (user_id, department_id) "
                "VALUES (:u, :d) ON CONFLICT DO NOTHING"
            ),
            {"u": user_id, "d": department_id},
        )
    await session.flush()
    return result, id_map


async def _migrate_contractors(
    session: AsyncSession, contract_rows: list[dict[str, Any]]
) -> tuple[EntityResult, dict[str, int]]:
    """Dedueix adjudicataris de les files de contracte (v1 no en tenia taula)."""
    variants: dict[str, Counter[str]] = {}
    for row in contract_rows:
        tax_id = (row.get("nif_adjudicatario") or "").strip().upper()
        name = (row.get("adjudicatario") or "").strip()
        if tax_id and name:
            variants.setdefault(tax_id, Counter())[name] += 1

    result = EntityResult(read=len(variants))
    tax_map: dict[str, int] = {}
    for tax_id, names in variants.items():
        canonical = names.most_common(1)[0][0]
        contractor = (
            await session.execute(select(Contractor).where(Contractor.tax_id == tax_id).limit(1))
        ).scalar_one_or_none()
        if contractor is None:
            contractor = Contractor(canonical_name=canonical, tax_id=tax_id)
            session.add(contractor)
            await session.flush()
            result.created += 1
        else:
            result.unchanged += 1
        tax_map[tax_id] = contractor.id

        # Les variants no canòniques queden com a àlies (idempotent).
        for variant in names:
            if variant == contractor.canonical_name:
                continue
            exists = (
                await session.execute(
                    select(ContractorAlias.id).where(ContractorAlias.alias == variant)
                )
            ).scalar_one_or_none()
            if exists is None:
                session.add(ContractorAlias(alias=variant, contractor_id=contractor.id))
    await session.flush()
    return result, tax_map


def _map_internal_status(value: Any) -> InternalStatus:
    mapped = source_map.INTERNAL_STATUS_MAP.get(str(value or "normal"), "normal")
    return InternalStatus(mapped)


async def _migrate_contracts(
    session: AsyncSession,
    rows: list[dict[str, Any]],
    department_links: list[dict[str, Any]],
    manager_links: list[dict[str, Any]],
    department_map: dict[int, int],
    user_map: dict[int, int],
    contractor_map: dict[str, int],
) -> tuple[EntityResult, dict[str, Any]]:
    result = EntityResult(read=len(rows))
    departments_of: dict[int, set[int]] = {}
    for link in department_links:
        departments_of.setdefault(link["contrato_id"], set()).add(link["departamento_id"])
    managers_of: dict[int, set[int]] = {}
    for link in manager_links:
        managers_of.setdefault(link["contrato_id"], set()).add(link["usuario_id"])

    checksum_v1 = Decimal(0)
    checksum_v2 = Decimal(0)
    matched = 0

    for row in rows:
        natural_key = (
            (row["expediente"] or "").strip(),
            (row["estado"] or "").strip(),
            (row["lote"] or "").strip(),
        )
        if not natural_key[0]:
            result.orphans.append(f"contracte v1 id={row['id']} sense expedient")
            continue
        contract = (
            await session.execute(
                select(Contract).where(
                    Contract.file_code == natural_key[0],
                    Contract.status == natural_key[1],
                    Contract.lot == natural_key[2],
                )
            )
        ).scalar_one_or_none()

        internal_status = _map_internal_status(row.get("estado_interno"))
        warning = row.get("meses_aviso_vencimiento")
        tax_id = (row.get("nif_adjudicatario") or "").strip().upper()

        if contract is None:
            # Només a la v1 (alta manual): s'insereix sencer com a local.
            contract = Contract(
                file_code=natural_key[0],
                status=natural_key[1] or "Desconegut",
                lot=natural_key[2],
                source=ContractSource.LOCAL,
                subject=row.get("objeto"),
                contract_type=row.get("tipo_contrato"),
                procedure=row.get("procedimiento"),
                award_amount=row.get("importe_adjudicacion"),
                published_at=row.get("fecha_publicacion"),
                start_date=row.get("fecha_inicio"),
                end_date=row.get("fecha_fin"),
                raw_contractor_name=row.get("adjudicatario"),
                contractor_id=contractor_map.get(tax_id),
                internal_status=internal_status,
                warning_months_override=warning,
            )
            session.add(contract)
            await session.flush()
            result.created += 1
        else:
            matched += 1
            checksum_v1 += Decimal(str(row.get("importe_adjudicacion") or 0))
            checksum_v2 += contract.award_amount or Decimal(0)
            before = (contract.internal_status, contract.warning_months_override)
            contract.internal_status = internal_status
            contract.warning_months_override = warning
            if before == (internal_status, warning):
                result.unchanged += 1
            else:
                result.updated += 1

        # Gestió local: departaments i responsables — l'últim valor v1 mana.
        v2_departments = {
            department_map[d] for d in departments_of.get(row["id"], set()) if d in department_map
        }
        await session.execute(
            text("DELETE FROM contract_departments WHERE contract_id = :c"),
            {"c": contract.id},
        )
        for department_id in sorted(v2_departments):
            await session.execute(
                text(
                    "INSERT INTO contract_departments (contract_id, department_id) "
                    "VALUES (:c, :d) ON CONFLICT DO NOTHING"
                ),
                {"c": contract.id, "d": department_id},
            )
        v2_managers = set()
        for v1_user in managers_of.get(row["id"], set()):
            if v1_user in user_map:
                v2_managers.add(user_map[v1_user])
            else:
                result.orphans.append(
                    f"contracte {natural_key[0]}: responsable v1 id={v1_user} no migrat"
                )
        await session.execute(
            text("DELETE FROM contract_managers WHERE contract_id = :c"), {"c": contract.id}
        )
        for manager_id in sorted(v2_managers):
            await session.execute(
                text(
                    "INSERT INTO contract_managers (contract_id, user_id) "
                    "VALUES (:c, :u) ON CONFLICT DO NOTHING"
                ),
                {"c": contract.id, "u": manager_id},
            )

    await session.flush()
    checksums = {
        "matched_contracts": matched,
        "award_amount_v1": str(checksum_v1),
        "award_amount_v2": str(checksum_v2),
    }
    return result, checksums


async def _migrate_minors(
    session: AsyncSession,
    rows: list[dict[str, Any]],
    department_links: list[dict[str, Any]],
    department_map: dict[int, int],
) -> EntityResult:
    result = EntityResult(read=len(rows))
    departments_of: dict[int, set[int]] = {}
    for link in department_links:
        departments_of.setdefault(link["contrato_menor_id"], set()).add(link["departamento_id"])
    for row in rows:
        file_code = (row["expediente"] or "").strip()
        minor = (
            await session.execute(select(MinorContract).where(MinorContract.file_code == file_code))
        ).scalar_one_or_none()
        if minor is None:
            result.orphans.append(f"menor v1 {file_code!r} sense parella v2")
            continue
        internal_status = _map_internal_status(row.get("estado_interno"))
        changed = minor.internal_status != internal_status
        minor.internal_status = internal_status

        v2_departments = {
            department_map[d] for d in departments_of.get(row["id"], set()) if d in department_map
        }
        await session.execute(
            text("DELETE FROM minor_contract_departments WHERE minor_contract_id = :m"),
            {"m": minor.id},
        )
        for department_id in sorted(v2_departments):
            await session.execute(
                text(
                    "INSERT INTO minor_contract_departments (minor_contract_id, department_id)"
                    " VALUES (:m, :d) ON CONFLICT DO NOTHING"
                ),
                {"m": minor.id, "d": department_id},
            )
        if changed:
            result.updated += 1
        else:
            result.unchanged += 1
    await session.flush()
    return result


async def run_migration(
    source_dsn: str,
    *,
    schema: str = source_map.DEFAULT_SCHEMA,
    dry_run: bool = False,
) -> dict[str, Any]:
    source = await _read_source(source_dsn, schema)

    results: dict[str, Any] = {"dry_run": dry_run}
    async with session_factory() as session:
        departments, department_map = await _migrate_departments(session, source["departments"])
        users, user_map = await _migrate_users(
            session, source["users"], source["user_departments"], department_map
        )
        contractors, contractor_map = await _migrate_contractors(session, source["contracts"])
        contracts, checksums = await _migrate_contracts(
            session,
            source["contracts"],
            source["contract_departments"],
            source["contract_managers"],
            department_map,
            user_map,
            contractor_map,
        )
        minors = await _migrate_minors(
            session,
            source["minor_contracts"],
            source["minor_contract_departments"],
            department_map,
        )

        results["entities"] = {
            "departments": departments.as_dict(),
            "users": users.as_dict(),
            "contractors": contractors.as_dict(),
            "contracts": contracts.as_dict(),
            "minor_contracts": minors.as_dict(),
        }
        results["checksums"] = checksums
        results["pending"] = [
            "settings (re-xifrat de secrets)",
            "pla anual / carpetes / projectes documentals",
            "historial_contratos i sincronizaciones (llegats)",
            "contrasenyes locals: restabliment necessari (KDF v1 incompatible)",
        ]

        if dry_run:
            await session.rollback()
        else:
            await record_audit(
                session,
                actor_type=AuditActorType.SYSTEM,
                action="migration.run",
                success=True,
                resource_type="migration",
                resource_id="v1",
                details={
                    entity: {k: v for k, v in data.items() if k != "orphans"}
                    for entity, data in results["entities"].items()
                },
            )
            await session.commit()

    logger.info("migration_finished", dry_run=dry_run, checksums=checksums)
    return results
