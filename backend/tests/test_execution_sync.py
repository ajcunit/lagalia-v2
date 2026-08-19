"""Sincronització de la fase d'execució (specs/execution-sync.md, B-017)."""

from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.core.db import session_factory
from app.integrations.socrata import sync_execution
from tests.conftest import login_headers

pytestmark = pytest.mark.anyio


def _record(tag: str, **extra: str) -> dict[str, str]:
    return {
        "codi_expedient": f"EXE/{tag}",
        "numero_lot": "1",
        "tipus_actuacio_execucio": "Modificació de contracte",
        "denominacio_actuacio": "Ampliació del servei",
        "data": "2026-03-01T00:00:00.000",
        "data_fi": "2026-12-31T00:00:00.000",
        "import_sense_iva": "1234.50",
        "identificacio": "B12345678",
        "denominacio": "Empresa d'Execució SL",
        "observacions": "Aprovada per JGL",
        "url_json": "https://contractaciopublica.cat/x/y",
        **extra,
    }


def test_execution_values_defaults_and_override() -> None:
    record = _record("MAP", camp_alternatiu="Actuació alternativa")
    values = sync_execution.execution_values(record)
    assert values["action_type"] == "Modificació de contracte"
    assert values["date"] == date(2026, 3, 1)
    assert str(values["amount"]) == "1234.50"
    assert values["contractor_tax_id"] == "B12345678"

    overridden = sync_execution.execution_values(
        record, {"execution.action_name": "camp_alternatiu"}
    )
    assert overridden["action_name"] == "Actuació alternativa"


async def test_upsert_matching_and_api_scope(api_client, make_user) -> None:  # type: ignore[no-untyped-def]
    admin_user = await make_user("admin")
    dm_other = await make_user("dept_manager")
    admin = login_headers(api_client, admin_user.email)
    tag = uuid4().hex[:8]
    record = _record(tag)

    # Sense contracte local → unmatched (es desa igualment).
    async with session_factory() as session:
        outcome = await sync_execution._upsert_execution(session, record, None)
        await session.commit()
    assert outcome == "unmatched"

    # Idempotència per hash.
    async with session_factory() as session:
        outcome = await sync_execution._upsert_execution(session, record, None)
        await session.commit()
    assert outcome == "unchanged"

    # Quan l'expedient arriba, el vincle es refà a la següent passada.
    async with session_factory() as session:
        dept_a = (
            await session.execute(
                text("INSERT INTO departments (code, name) VALUES (:c, 'ExeA') RETURNING id"),
                {"c": f"EA-{tag}"},
            )
        ).scalar_one()
        dept_b = (
            await session.execute(
                text("INSERT INTO departments (code, name) VALUES (:c, 'ExeB') RETURNING id"),
                {"c": f"EB-{tag}"},
            )
        ).scalar_one()
        await session.execute(
            text("INSERT INTO user_departments (user_id, department_id) VALUES (:u, :d)"),
            {"u": dm_other.id, "d": dept_a},
        )
        contract_id = (
            await session.execute(
                text(
                    "INSERT INTO contracts (file_code, status, lot, subject) "
                    "VALUES (:f, 'Formalització', '', 'Servei amb execució') RETURNING id"
                ),
                {"f": f"EXE/{tag}"},
            )
        ).scalar_one()
        await session.execute(
            text("INSERT INTO contract_departments (contract_id, department_id) VALUES (:c, :d)"),
            {"c": contract_id, "d": dept_b},
        )
        outcome = await sync_execution._upsert_execution(session, record, None)
        await session.commit()
    assert outcome == "updated"  # relink

    # Subrecurs amb abast: admin veu l'actuació; cap d'un altre departament → 404.
    listing = api_client.get(f"/api/v1/contracts/{contract_id}/executions", headers=admin)
    assert listing.status_code == 200, listing.text
    rows = listing.json()["data"]
    assert len(rows) == 1
    assert rows[0]["action_type"] == "Modificació de contracte"
    assert rows[0]["contractor_name"] == "Empresa d'Execució SL"
    assert (
        api_client.get(
            f"/api/v1/contracts/{contract_id}/executions",
            headers=login_headers(api_client, dm_other.email),
        ).status_code
        == 404
    )

    # Font `execution` al mapejador.
    mappings = api_client.get("/api/v1/field-mappings/execution", headers=admin)
    assert mappings.status_code == 200
    targets = {row["target_field"] for row in mappings.json()["data"]}
    assert "execution.action_type" in targets

    # Remap local des del raw amb override persistit.
    saved = api_client.put(
        "/api/v1/field-mappings/execution/execution.action_name",
        json={"source_field": "observacions"},
        headers=admin,
    )
    assert saved.status_code == 200, saved.text

    class Ctx:
        payload: dict = {}

        async def set_progress(self, *a, **k) -> None:  # type: ignore[no-untyped-def]
            return None

    result = await sync_execution.remap_execution(Ctx())  # type: ignore[arg-type]
    assert result["failed"] == 0

    async with session_factory() as session:
        row = (
            await session.execute(
                text("SELECT action_name FROM contract_executions WHERE file_code = :f"),
                {"f": f"EXE/{tag}"},
            )
        ).first()
        # Neteja.
        await session.execute(
            text("DELETE FROM contract_executions WHERE file_code = :f"), {"f": f"EXE/{tag}"}
        )
        await session.execute(
            text(
                "DELETE FROM field_mappings WHERE source = 'execution' "
                "AND target_field = 'execution.action_name'"
            )
        )
        await session.execute(text("DELETE FROM contracts WHERE id = :i"), {"i": contract_id})
        await session.execute(
            text("DELETE FROM departments WHERE id IN (:a, :b)"), {"a": dept_a, "b": dept_b}
        )
        await session.commit()
    assert row.action_name == "Aprovada per JGL"


def test_extract_execution_detail() -> None:
    """Extracció del JSON de detall (estructura real del portal, 300731659)."""
    detail = {
        "publicacio": {
            "dadesPublicacioLot": [
                {
                    "modificacions": [
                        {
                            "supositHabilitant": {
                                "id": 1008336,
                                "ca": "No prevista en plecs (art. 205.2.c LCSP)",
                                "en": "Not anticipated",
                            },
                            "informeJustificatiu": {
                                "ca": [
                                    {
                                        "id": 302189629,
                                        "titol": "Informe jurídic.pdf",
                                        "hash": "37C1F290",
                                        "mida": 333817,
                                    }
                                ]
                            },
                            "resolucioModificacio": {
                                "ca": [
                                    {
                                        "id": 302189625,
                                        "titol": "Certificat modificació.pdf",
                                        "hash": "DFB3A8AA",
                                        "mida": 599575,
                                    }
                                ]
                            },
                        }
                    ]
                }
            ]
        }
    }
    extracted = sync_execution.extract_execution_detail(detail, "https://contractaciopublica.cat")
    assert extracted["suposit_habilitant"] == "No prevista en plecs (art. 205.2.c LCSP)"
    groups = {d["group"] for d in extracted["documents"]}
    assert groups == {"informeJustificatiu", "resolucioModificacio"}
    informe = next(d for d in extracted["documents"] if d["group"] == "informeJustificatiu")
    assert informe["title"] == "Informe jurídic.pdf"
    assert informe["size"] == 333817
    assert informe["download_url"].startswith(
        "https://contractaciopublica.cat/portal-api/descarrega-document/302189629/"
    )
    # Fora dels grups coneguts no s'arrepleguen documents.
    stray = {"altresCoses": {"id": 1, "titol": "x.pdf", "hash": "A"}}
    assert sync_execution.extract_execution_detail(stray, "https://x")["documents"] == []
