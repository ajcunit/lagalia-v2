"""Migració v1→v2 contra un esquema v1 sintètic (mateix source_map)."""

from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.crypto import decrypt_value
from app.core.db import session_factory
from app.migration import source_map
from app.migration.migrate import run_migration
from app.migration.report import write_report

pytestmark = pytest.mark.usefixtures("v1_schema")

SCHEMA = "v1_mig_test"


@pytest.fixture
async def v1_schema() -> AsyncIterator[dict[str, Any]]:
    """Esquema v1 sintètic + un contracte v2 preexistent per conciliar."""
    tag = uuid4().hex[:8]
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
        for ddl in source_map.synthetic_ddl(SCHEMA):
            await conn.execute(text(ddl))

        # v1: departament, usuaris, contractes.
        await conn.execute(
            text(f"INSERT INTO {SCHEMA}.departamentos (id, nombre) VALUES (1, :n)"),
            {"n": f"Urbanisme Migració {tag}"},
        )
        await conn.execute(
            text(
                f"INSERT INTO {SCHEMA}.usuarios "
                "(id, nombre, email, rol, dni, permiso_auditoria) VALUES "
                "(1, 'Responsable Mig', :e1, 'responsable', '12345678Z', true), "
                "(2, 'Empleada Mig', :e2, 'empleado', NULL, false), "
                "(3, 'Rol Estrany', :e3, 'superadmin', NULL, false)"
            ),
            {
                "e1": f"mig-resp-{tag}@cunit.cat",
                "e2": f"mig-emp-{tag}@cunit.cat",
                "e3": f"mig-x-{tag}@cunit.cat",
            },
        )
        await conn.execute(
            text(
                f"INSERT INTO {SCHEMA}.usuarios_departamentos "
                "(usuario_id, departamento_id) VALUES (1, 1), (2, 1)"
            )
        )
        # Contracte 1: existeix a la v2 (sincronitzat). Contracte 2: només v1.
        # El NIF es repeteix amb dues variants de nom (dedup + àlies).
        await conn.execute(
            text(
                f"INSERT INTO {SCHEMA}.contratos (id, expediente, estado, lote, objeto, "
                "adjudicatario, nif_adjudicatario, importe_adjudicacion, estado_interno, "
                "meses_aviso_vencimiento) VALUES "
                "(1, :f1, 'Formalització', '', 'Objecte sincronitzat', "
                " 'EMPRESA MIG S.L.', :nif, 111.50, 'pendiente_aprobacion', 4), "
                "(2, :f2, 'Manual', '', 'Alta manual v1', "
                " 'EMPRESA MIG SL', :nif, 222.25, 'aprobado', NULL)"
            ),
            {"f1": f"MIG-{tag}/1", "f2": f"MIG-{tag}/2", "nif": f"B{tag[:7].upper()}9"},
        )
        await conn.execute(
            text(
                f"INSERT INTO {SCHEMA}.contratos_departamentos "
                "(contrato_id, departamento_id) VALUES (1, 1), (2, 1)"
            )
        )
        await conn.execute(
            text(
                f"INSERT INTO {SCHEMA}.contratos_responsables "
                "(contrato_id, usuario_id) VALUES (1, 1)"
            )
        )
        await conn.execute(
            text(
                f"INSERT INTO {SCHEMA}.contratos_menores (id, expediente, estado_interno) "
                "VALUES (1, :f, 'aprobado'), (2, :orfe, 'normal')"
            ),
            {"f": f"MIGM-{tag}/1", "orfe": f"MIGM-{tag}/orfe"},
        )
        await conn.execute(
            text(
                f"INSERT INTO {SCHEMA}.contratos_menores_departamentos "
                "(contrato_menor_id, departamento_id) VALUES (1, 1)"
            )
        )

        # v2 preexistent: el contracte sincronitzat i un menor.
        await conn.execute(
            text(
                "INSERT INTO contracts (file_code, status, lot, subject, award_amount) "
                "VALUES (:f, 'Formalització', '', 'Objecte sincronitzat', 111.50)"
            ),
            {"f": f"MIG-{tag}/1"},
        )
        await conn.execute(
            text("INSERT INTO minor_contracts (file_code) VALUES (:f)"),
            {"f": f"MIGM-{tag}/1"},
        )
    await engine.dispose()

    yield {"tag": tag}

    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
        await conn.execute(
            text("DELETE FROM contracts WHERE file_code LIKE :p"), {"p": f"MIG-{tag}%"}
        )
        await conn.execute(
            text("DELETE FROM minor_contracts WHERE file_code LIKE :p"), {"p": f"MIGM-{tag}%"}
        )
        await conn.execute(
            text("DELETE FROM contractors WHERE tax_id = :t"), {"t": f"B{tag[:7].upper()}9"}
        )
        await conn.execute(
            text("DELETE FROM users WHERE email LIKE :p"), {"p": f"mig-%-{tag}@cunit.cat"}
        )
        await conn.execute(
            text("DELETE FROM departments WHERE name LIKE :p"), {"p": f"Urbanisme Migració {tag}"}
        )
    await engine.dispose()


async def test_full_migration_and_idempotency(v1_schema: dict[str, Any], tmp_path: Any) -> None:
    tag = v1_schema["tag"]
    results = await run_migration(settings.database_url, schema=SCHEMA)

    entities = results["entities"]
    assert entities["departments"]["created"] == 1
    assert entities["users"]["created"] == 2  # el rol desconegut queda orfe
    assert any("superadmin" in o for o in entities["users"]["orphans"])
    assert entities["contractors"]["created"] == 1
    assert entities["contracts"]["created"] == 1  # el manual v1
    assert entities["contracts"]["updated"] == 1  # el sincronitzat (estat intern)
    assert entities["minor_contracts"]["updated"] == 1
    assert any("orfe" in o for o in entities["minor_contracts"]["orphans"])
    assert results["checksums"]["matched_contracts"] == 1
    assert results["checksums"]["award_amount_v1"] == results["checksums"]["award_amount_v2"]

    async with session_factory() as session:
        # Camps locals copiats al contracte sincronitzat; els de font intactes.
        synced = (
            (
                await session.execute(
                    text(
                        "SELECT internal_status, warning_months_override, subject, "
                        "award_amount FROM contracts WHERE file_code = :f AND lot = ''"
                    ),
                    {"f": f"MIG-{tag}/1"},
                )
            )
            .mappings()
            .one()
        )
        assert synced["internal_status"] == "pending_review"
        assert synced["warning_months_override"] == 4
        assert synced["subject"] == "Objecte sincronitzat"

        # El manual v1 és local, amb adjudicatari dedupat per NIF.
        local = (
            (
                await session.execute(
                    text(
                        "SELECT source, internal_status, contractor_id FROM contracts "
                        "WHERE file_code = :f"
                    ),
                    {"f": f"MIG-{tag}/2"},
                )
            )
            .mappings()
            .one()
        )
        assert local["source"] == "local"
        assert local["internal_status"] == "approved"
        assert local["contractor_id"] is not None

        # Variant de nom com a àlies; DNI xifrat i recuperable.
        alias = (
            await session.execute(
                text(
                    "SELECT a.alias FROM contractor_aliases a "
                    "JOIN contractors c ON c.id = a.contractor_id WHERE c.tax_id = :t"
                ),
                {"t": f"B{tag[:7].upper()}9"},
            )
        ).scalars()
        assert set(alias) >= {"EMPRESA MIG SL"} or set(alias) >= {"EMPRESA MIG S.L."}
        dni_blob = (
            await session.execute(
                text("SELECT dni_encrypted FROM users WHERE email = :e"),
                {"e": f"mig-resp-{tag}@cunit.cat"},
            )
        ).scalar_one()
        assert decrypt_value(dni_blob) == "12345678Z"

        # Responsable assignat per la migració.
        manager = (
            await session.execute(
                text(
                    "SELECT count(*) FROM contract_managers cm "
                    "JOIN contracts c ON c.id = cm.contract_id WHERE c.file_code = :f"
                ),
                {"f": f"MIG-{tag}/1"},
            )
        ).scalar_one()
        assert manager == 1

    # Re-run: idempotent, res de nou.
    rerun = await run_migration(settings.database_url, schema=SCHEMA)
    assert rerun["entities"]["departments"]["created"] == 0
    assert rerun["entities"]["users"]["created"] == 0
    assert rerun["entities"]["contractors"]["created"] == 0
    assert rerun["entities"]["contracts"]["created"] == 0
    # Els dos contractes ja concilien (el sincronitzat i el local de la 1a passada).
    assert rerun["entities"]["contracts"]["unchanged"] == 2
    assert rerun["checksums"]["matched_contracts"] == 2

    # Informe generat.
    report = write_report(rerun, tmp_path)
    assert report.exists()
    content = report.read_text(encoding="utf-8")
    assert "Informe de reconciliació" in content
    assert "contractors" in content


async def test_dry_run_writes_nothing(v1_schema: dict[str, Any]) -> None:
    tag = v1_schema["tag"]
    results = await run_migration(settings.database_url, schema=SCHEMA, dry_run=True)
    assert results["dry_run"] is True
    assert results["entities"]["contracts"]["created"] == 1  # calculat…

    async with session_factory() as session:
        count = (
            await session.execute(
                text("SELECT count(*) FROM contracts WHERE file_code = :f"),
                {"f": f"MIG-{tag}/2"},
            )
        ).scalar_one()
        assert count == 0  # …però no escrit
