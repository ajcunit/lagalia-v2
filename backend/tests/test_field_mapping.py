"""Mapejador de camps font → model (specs/field-mapping.md)."""

from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.core.db import session_factory
from app.integrations.socrata import mapping
from tests.conftest import login_headers

pytestmark = pytest.mark.anyio


def test_parse_duration_range() -> None:
    # Cas real 2885/2026: rang de dates en lloc de durada.
    assert mapping.parse_duration_range("15/06/2026 a 14/06/2027") == (
        date(2026, 6, 15),
        date(2027, 6, 14),
    )
    assert mapping.parse_duration_range("12") is None
    assert mapping.parse_duration_range("1 anys 0 mesos 0 dies") is None
    assert mapping.parse_duration_range(None) is None
    # Rang invertit → invàlid.
    assert mapping.parse_duration_range("14/06/2027 a 15/06/2026") is None


def test_months_between() -> None:
    assert mapping.months_between(date(2026, 6, 15), date(2027, 6, 14)) == 12
    assert mapping.months_between(date(2026, 1, 1), date(2026, 6, 30)) == 6
    assert mapping.months_between(date(2026, 3, 1), date(2026, 3, 28)) == 1


def test_map_contract_duration_range_and_override() -> None:
    record = {
        "codi_expedient": "2885/2026",
        "resultat": "Formalització",
        "data_formalitzacio_contracte": "2026-06-11T00:00:00.000",
        "durada_contracte": "15/06/2026 a 14/06/2027",
        "objecte_contracte": "Servei del cementiri",
        "camp_alternatiu": "Objecte alternatiu",
    }
    mapped = mapping.map_contract(record)
    # El rang mana: inici/fi/durada surten del rang, no del càlcul A1.
    assert mapped["start_date"] == date(2026, 6, 15)
    assert mapped["end_date"] == date(2027, 6, 14)
    assert mapped["calculated_end_date"] == date(2027, 6, 14)
    assert mapped["duration_months"] == 12
    assert mapped["subject"] == "Servei del cementiri"

    # Override manual: subject llegeix un altre camp de la font.
    remapped = mapping.map_contract(record, {"subject": "camp_alternatiu"})
    assert remapped["subject"] == "Objecte alternatiu"
    # La resta no canvia.
    assert remapped["duration_months"] == 12


def test_map_contract_classic_duration_still_works() -> None:
    record = {
        "codi_expedient": "X/2026",
        "resultat": "Formalització",
        "data_formalitzacio_contracte": "2026-01-10T00:00:00.000",
        "durada_contracte": "12",
    }
    mapped = mapping.map_contract(record)
    assert mapped["duration_months"] == 12
    assert mapped["start_date"] == date(2026, 1, 11)


async def test_field_mapping_api_and_remap(api_client, make_user) -> None:  # type: ignore[no-untyped-def]
    admin_user = await make_user("admin")
    employee = await make_user("employee")
    admin = login_headers(api_client, admin_user.email)

    # Llistat amb defectes de l'annex A1.
    listing = api_client.get("/api/v1/field-mappings/socrata", headers=admin)
    assert listing.status_code == 200, listing.text
    rows = {row["target_field"]: row for row in listing.json()["data"]}
    assert rows["duration_months"]["default_source_field"] == "durada_contracte"
    assert rows["duration_months"]["overridden"] is False
    assert "contractor.name" in rows

    # Font sense mapejador → 404; escriptura sense permís → 403.
    assert (
        api_client.get("/api/v1/field-mappings/smtp", headers=admin).status_code == 404
    )
    assert (
        api_client.put(
            "/api/v1/field-mappings/socrata/subject",
            json={"source_field": "camp_nou"},
            headers=login_headers(api_client, employee.email),
        ).status_code
        == 403
    )

    # Override: destí desconegut → 404; camp font invàlid → 422; vàlid → desat.
    assert (
        api_client.put(
            "/api/v1/field-mappings/socrata/camp_inventat",
            json={"source_field": "x"},
            headers=admin,
        ).status_code
        == 404
    )
    assert (
        api_client.put(
            "/api/v1/field-mappings/socrata/subject",
            json={"source_field": "amb espais!"},
            headers=admin,
        ).status_code
        == 422
    )
    saved = api_client.put(
        "/api/v1/field-mappings/socrata/subject",
        json={"source_field": "denominacio"},
        headers=admin,
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["overridden"] is True

    # L'override persistit surt al llistat i s'aplica al mapeig.
    listing2 = api_client.get("/api/v1/field-mappings/socrata", headers=admin)
    subject_row = next(
        r for r in listing2.json()["data"] if r["target_field"] == "subject"
    )
    assert subject_row["source_field"] == "denominacio"
    assert subject_row["overridden"] is True

    # Contracte guardat amb raw: mostra + remap.
    tag = uuid4().hex[:8]
    raw = {
        "codi_expedient": f"MAP/{tag}",
        "resultat": "Formalització",
        "denominacio": "Nom curt de la font",
        "objecte_contracte": "Objecte llarg original",
        "data_formalitzacio_contracte": "2026-06-11T00:00:00.000",
        "durada_contracte": "15/06/2026 a 14/06/2027",
    }
    import json as _json

    async with session_factory() as session:
        contract_id = (
            await session.execute(
                text(
                    "INSERT INTO contracts (file_code, status, lot, subject, raw) "
                    "VALUES (:f, 'Formalització', '', 'Objecte antic', CAST(:r AS jsonb)) "
                    "RETURNING id"
                ),
                {"f": f"MAP/{tag}", "r": _json.dumps(raw)},
            )
        ).scalar_one()
        await session.commit()

    sample = api_client.get(
        "/api/v1/field-mappings/socrata/sample",
        params={"file_code": f"MAP/{tag}"},
        headers=admin,
    )
    assert sample.status_code == 200, sample.text
    assert sample.json()["fields"]["durada_contracte"] == "15/06/2026 a 14/06/2027"
    assert (
        api_client.get(
            "/api/v1/field-mappings/socrata/sample",
            params={"file_code": "NOEXISTEIX/999"},
            headers=admin,
        ).status_code
        == 404
    )

    # Remap local: aplica overrides + rang de durada al raw guardat.
    from app.integrations.field_mappings import remap_contracts

    class Ctx:
        payload: dict = {}

        async def set_progress(self, *_args, **_kwargs) -> None:
            return None

    result = await remap_contracts(Ctx())  # type: ignore[arg-type]
    assert result["failed"] == 0
    assert result["updated"] >= 1

    async with session_factory() as session:
        row = (
            await session.execute(
                text(
                    "SELECT subject, start_date, end_date, duration_months "
                    "FROM contracts WHERE id = :i"
                ),
                {"i": contract_id},
            )
        ).first()
        history = (
            await session.execute(
                text(
                    "SELECT count(*) FROM contract_history "
                    "WHERE contract_id = :i AND change_type = 'sync'"
                ),
                {"i": contract_id},
            )
        ).scalar_one()
    assert row.subject == "Nom curt de la font"  # override aplicat
    assert row.start_date == date(2026, 6, 15)
    assert row.end_date == date(2027, 6, 14)
    assert row.duration_months == 12
    assert history >= 3

    # Acció remap per API (202) + neteja.
    queued = api_client.post("/api/v1/field-mappings/socrata/actions/remap", headers=admin)
    assert queued.status_code == 202, queued.text
    assert (
        api_client.post(
            "/api/v1/field-mappings/smtp/actions/remap", headers=admin
        ).status_code
        == 404
    )

    reset = api_client.delete(
        "/api/v1/field-mappings/socrata/subject", headers=admin
    )
    assert reset.status_code == 204
    listing3 = api_client.get("/api/v1/field-mappings/socrata", headers=admin)
    subject_after = next(
        r for r in listing3.json()["data"] if r["target_field"] == "subject"
    )
    assert subject_after["overridden"] is False

    async with session_factory() as session:
        await session.execute(
            text("DELETE FROM contracts WHERE id = :i"), {"i": contract_id}
        )
        await session.execute(
            text("DELETE FROM jobs WHERE type = 'sync.remap_contracts'")
        )
        await session.commit()


def test_rpc_overrides_in_merge() -> None:
    from app.integrations.socrata.sync_rpc import extension_values, merge_minor_records

    award = {
        "situaci_contractual": "Menor",
        "tipus_contracte": "Serveis",
        "contracte": "Servei de prova",
        "descripcio_alternativa": "Descripció alternativa",
        "import_adjudicacio": "1000.50",
        "data_adjudicacio": "2026-02-01T00:00:00.000",
        "exercici": "2026",
    }
    values = merge_minor_records("M/1", [award])
    assert values is not None and values["description"] == "Servei de prova"

    overridden = merge_minor_records(
        "M/1", [award], {"minor.description": "descripcio_alternativa"}
    )
    assert overridden is not None
    assert overridden["description"] == "Descripció alternativa"
    assert str(overridden["award_amount"]) == "1000.50"

    extension = {
        "data_inici_prorroga": "2026-01-01T00:00:00.000",
        "data_fi_prorroga": "2026-12-31T00:00:00.000",
        "import_adjudicacio": "500",
        "camp_import_alternatiu": "999",
        "exercici": "2026",
    }
    assert str(extension_values(extension)["amount"]) == "500"
    assert (
        str(extension_values(extension, {"extension.amount": "camp_import_alternatiu"})["amount"])
        == "999"
    )


def test_pscp_path_overrides() -> None:
    import json
    from pathlib import Path

    from app.integrations.pscp import extract

    fixtures = Path(__file__).parent / "fixtures"
    licitacio = json.loads((fixtures / "pscp_licitacio.json").read_text(encoding="utf-8"))

    # Comportament per defecte intacte (fixture real).
    base = extract.extract_scalars("licitacio", licitacio)
    assert "is_harmonized" in base or "place_of_execution" in base

    # path_get resol camins amb índexs.
    assert extract.path_get({"a": {"b": [{"c": 7}]}}, "a.b[0].c") == 7
    assert extract.path_get({"a": {}}, "a.b[0].c") is None

    # Override per camí: un escalar llegeix un altre camp del JSON.
    payload = {
        "publicacio": {
            "dadesPublicacio": {"contracteHarmonitzat": False, "campAlternatiu": True},
            "dadesPublicacioLot": [{"llocExecucio": {"ca": "Cunit"}}],
        }
    }
    default = extract.extract_scalars("licitacio", payload)
    assert default.get("is_harmonized") is False
    overridden = extract.extract_scalars(
        "licitacio", payload, {"is_harmonized": "publicacio.dadesPublicacio.campAlternatiu"}
    )
    assert overridden.get("is_harmonized") is True
    assert overridden.get("place_of_execution") == "Cunit"

    # flatten_paths exposa els camins per a la UI del mapejador.
    flattened = extract.flatten_paths(payload)
    assert flattened["publicacio.dadesPublicacio.contracteHarmonitzat"] is False
    assert flattened["publicacio.dadesPublicacioLot[0].llocExecucio.ca"] == "Cunit"


async def test_field_mapping_sources_api(api_client, make_user) -> None:  # type: ignore[no-untyped-def]
    admin_user = await make_user("admin")
    admin = login_headers(api_client, admin_user.email)

    # rpc i pscp llisten els seus registres.
    rpc = api_client.get("/api/v1/field-mappings/rpc", headers=admin)
    assert rpc.status_code == 200, rpc.text
    rpc_rows = {r["target_field"] for r in rpc.json()["data"]}
    assert "minor.award_amount" in rpc_rows and "extension.end_date" in rpc_rows

    pscp = api_client.get("/api/v1/field-mappings/pscp", headers=admin)
    assert pscp.status_code == 200, pscp.text
    pscp_rows = {r["target_field"]: r for r in pscp.json()["data"]}
    assert pscp_rows["award_amount"]["phases"] == ["adjudicacio", "formalitzacio"]

    # pscp accepta camins; els camps plans no.
    ok = api_client.put(
        "/api/v1/field-mappings/pscp/award_amount",
        json={"source_field": "publicacio.dadesPublicacioLot[0].importFormalitzacio"},
        headers=admin,
    )
    assert ok.status_code == 200, ok.text
    bad = api_client.put(
        "/api/v1/field-mappings/socrata/subject",
        json={"source_field": "a.b[0].c"},
        headers=admin,
    )
    assert bad.status_code == 422
    assert (
        api_client.delete("/api/v1/field-mappings/pscp/award_amount", headers=admin).status_code
        == 204
    )

    # Mostra RPC des del raw guardat d'un menor.
    from uuid import uuid4

    tag = uuid4().hex[:8]
    import json as _json

    async with session_factory() as session:
        minor_id = (
            await session.execute(
                text(
                    "INSERT INTO minor_contracts (file_code, raw_award) "
                    "VALUES (:f, CAST(:r AS jsonb)) RETURNING id"
                ),
                {
                    "f": f"MENOR/{tag}",
                    "r": _json.dumps(
                        {
                            "situaci_contractual": "Menor",
                            "tipus_contracte": "Serveis",
                            "exercici": "2026",
                        }
                    ),
                },
            )
        ).scalar_one()
        await session.commit()
    sample = api_client.get(
        "/api/v1/field-mappings/rpc/sample",
        params={"file_code": f"MENOR/{tag}"},
        headers=admin,
    )
    assert sample.status_code == 200, sample.text
    assert sample.json()["fields"]["tipus_contracte"] == "Serveis"

    # Remap RPC local (job directe).
    from app.integrations.field_mappings import remap_rpc

    class Ctx:
        payload: dict = {}

        async def set_progress(self, *_args, **_kwargs) -> None:
            return None

    result = await remap_rpc(Ctx())  # type: ignore[arg-type]
    assert result["failed"] == 0

    async with session_factory() as session:
        row = (
            await session.execute(
                text("SELECT contract_type, fiscal_year FROM minor_contracts WHERE id = :i"),
                {"i": minor_id},
            )
        ).first()
        await session.execute(
            text("DELETE FROM minor_contracts WHERE id = :i"), {"i": minor_id}
        )
        await session.execute(
            text("DELETE FROM jobs WHERE type IN ('sync.remap_rpc', 'enrich.batch')")
        )
        await session.commit()
    assert row.contract_type == "Serveis"
    assert row.fiscal_year == 2026
