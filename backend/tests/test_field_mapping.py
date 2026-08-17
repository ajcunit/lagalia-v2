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
    listing = api_client.get("/api/v1/connectors/socrata/field-mappings", headers=admin)
    assert listing.status_code == 200, listing.text
    rows = {row["target_field"]: row for row in listing.json()["data"]}
    assert rows["duration_months"]["default_source_field"] == "durada_contracte"
    assert rows["duration_months"]["overridden"] is False
    assert "contractor.name" in rows

    # Font sense mapejador → 404; escriptura sense permís → 403.
    assert (
        api_client.get("/api/v1/connectors/smtp/field-mappings", headers=admin).status_code == 404
    )
    assert (
        api_client.put(
            "/api/v1/connectors/socrata/field-mappings/subject",
            json={"source_field": "camp_nou"},
            headers=login_headers(api_client, employee.email),
        ).status_code
        == 403
    )

    # Override: destí desconegut → 404; camp font invàlid → 422; vàlid → desat.
    assert (
        api_client.put(
            "/api/v1/connectors/socrata/field-mappings/camp_inventat",
            json={"source_field": "x"},
            headers=admin,
        ).status_code
        == 404
    )
    assert (
        api_client.put(
            "/api/v1/connectors/socrata/field-mappings/subject",
            json={"source_field": "amb espais!"},
            headers=admin,
        ).status_code
        == 422
    )
    saved = api_client.put(
        "/api/v1/connectors/socrata/field-mappings/subject",
        json={"source_field": "denominacio"},
        headers=admin,
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["overridden"] is True

    # L'override persistit surt al llistat i s'aplica al mapeig.
    listing2 = api_client.get("/api/v1/connectors/socrata/field-mappings", headers=admin)
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
        "/api/v1/connectors/socrata/field-mappings/sample",
        params={"file_code": f"MAP/{tag}"},
        headers=admin,
    )
    assert sample.status_code == 200, sample.text
    assert sample.json()["fields"]["durada_contracte"] == "15/06/2026 a 14/06/2027"
    assert (
        api_client.get(
            "/api/v1/connectors/socrata/field-mappings/sample",
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
    queued = api_client.post("/api/v1/connectors/socrata/actions/remap", headers=admin)
    assert queued.status_code == 202, queued.text
    assert (
        api_client.post(
            "/api/v1/connectors/smtp/actions/remap", headers=admin
        ).status_code
        == 404
    )

    reset = api_client.delete(
        "/api/v1/connectors/socrata/field-mappings/subject", headers=admin
    )
    assert reset.status_code == 204
    listing3 = api_client.get("/api/v1/connectors/socrata/field-mappings", headers=admin)
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
