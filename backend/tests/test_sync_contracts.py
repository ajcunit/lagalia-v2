"""Sync de contractes de punta a punta (BD real, Socrata simulat)."""

import json
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.db import session_factory
from app.integrations import hub
from app.integrations.socrata.client import SocrataClient
from app.integrations.socrata.connector import SocrataConnector
from app.integrations.socrata.sync import sync_contracts

INE10 = "4305160009"


class FakeSocrata:
    """Servidor Socrata simulat: llista mutable + captura de peticions."""

    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []
        self.requests: list[dict[str, str]] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        self.requests.append(params)
        offset = int(params.get("$offset", 0))
        limit = int(params.get("$limit", 1000))
        return httpx.Response(200, json=self.records[offset : offset + limit])

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)


@pytest.fixture
async def fake_socrata(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[FakeSocrata]:
    fake = FakeSocrata()
    monkeypatch.setattr(
        SocrataConnector,
        "client",
        lambda self: SocrataClient(
            "https://fake.socrata.test", min_interval_seconds=0, transport=fake.transport()
        ),
    )

    created_setting = False
    async with session_factory() as session:
        record = await hub.ensure_registered(session, "socrata")
        was_enabled = record.enabled
        was_config = record.config
        record.enabled = True
        # El dataset simulat sí que té data_actualitzacio: incremental actiu.
        record.config = {"incremental_field": "data_actualitzacio"}
        existing = (
            await session.execute(text("SELECT id FROM settings WHERE key = 'org.ine10_code'"))
        ).scalar_one_or_none()
        if existing is None:
            await session.execute(
                text("INSERT INTO settings (key, value) VALUES ('org.ine10_code', :v)"),
                {"v": json.dumps(INE10)},
            )
            created_setting = True
        await session.commit()

    yield fake

    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    async with engine.begin() as conn:
        if created_setting:
            await conn.execute(text("DELETE FROM settings WHERE key = 'org.ine10_code'"))
        await conn.execute(
            text("UPDATE connectors SET enabled = :e, config = :c WHERE slug = 'socrata'"),
            {"e": was_enabled, "c": json.dumps(was_config) if was_config else None},
        )
    await engine.dispose()


@pytest.fixture
async def scenario() -> AsyncIterator[dict[str, Any]]:
    """Departament + regla ('neteja' → dept) + adjudicatari amb àlies."""
    tag = uuid4().hex[:8]
    data: dict[str, Any] = {"tag": tag}
    async with session_factory() as session:
        dept_id = (
            await session.execute(
                text(
                    "INSERT INTO departments (code, name) "
                    "VALUES (:c, 'Departament Sync Test') RETURNING id"
                ),
                {"c": f"SYNC-{tag}"},
            )
        ).scalar_one()
        rule_id = (
            await session.execute(
                text(
                    "INSERT INTO association_rules "
                    "(department_id, rule_type, source_field, match_value, operator, priority) "
                    "VALUES (:d, 'keyword', 'subject', 'neteja', 'contains', 500) RETURNING id"
                ),
                {"d": dept_id},
            )
        ).scalar_one()
        canonical_id = (
            await session.execute(
                text(
                    "INSERT INTO contractors (canonical_name, tax_id) VALUES (:n, :t) RETURNING id"
                ),
                {"n": f"Jardineria Canònica {tag} SL", "t": f"B{tag.upper()[:7]}0"},
            )
        ).scalar_one()
        await session.execute(
            text("INSERT INTO contractor_aliases (alias, contractor_id) VALUES (:a, :c)"),
            {"a": f"JARDINERIA ALIAS {tag}", "c": canonical_id},
        )
        await session.commit()
        data.update(dept_id=dept_id, rule_id=rule_id, canonical_id=canonical_id)

    yield data

    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.execute(
            text("DELETE FROM contracts WHERE file_code LIKE :p"), {"p": f"EXP-{tag}%"}
        )
        await conn.execute(
            text("DELETE FROM association_rules WHERE id = :i"), {"i": data["rule_id"]}
        )
        await conn.execute(text("DELETE FROM departments WHERE id = :i"), {"i": data["dept_id"]})
        await conn.execute(
            text(
                "DELETE FROM contractor_duplicates WHERE contractor_id_1 IN "
                "(SELECT id FROM contractors WHERE canonical_name LIKE :p) "
                "OR contractor_id_2 IN (SELECT id FROM contractors WHERE canonical_name LIKE :p)"
            ),
            {"p": f"%{tag}%"},
        )
        await conn.execute(
            text("DELETE FROM contractors WHERE canonical_name LIKE :p"), {"p": f"%{tag}%"}
        )
        await conn.execute(
            text(
                "DELETE FROM sync_item_logs WHERE sync_run_id IN "
                "(SELECT id FROM sync_runs WHERE endpoint LIKE '%fake.socrata.test%')"
            )
        )
        await conn.execute(
            text(
                "DELETE FROM sync_runs WHERE endpoint LIKE '%fake.socrata.test%' "
                "OR status = 'failed'"
            )
        )
    await engine.dispose()


def _record(tag: str, *, code: str, subject: str, **extra: Any) -> dict[str, Any]:
    return {
        "codi_expedient": f"EXP-{tag}-{code}",
        "codi_ine10": INE10,
        "resultat": "Formalitzat",
        "objecte_contracte": subject,
        "data_formalitzacio_contracte": "2026-01-15",
        "durada_contracte": "12",
        "data_actualitzacio": "2026-06-01T10:00:00",
        **extra,
    }


async def _run_sync(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    from tests.conftest import make_job_context

    # Fila `jobs` real: la sync_run que crea el handler hi vincula el job_id.
    result = await sync_contracts(await make_job_context("sync.contracts", payload))
    assert result is not None
    return result


async def _contract(tag: str, code: str) -> dict[str, Any] | None:
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    async with engine.connect() as conn:
        row = (
            (
                await conn.execute(
                    text(
                        "SELECT c.*, "
                        "(SELECT array_agg(department_id) FROM contract_departments cd "
                        " WHERE cd.contract_id = c.id) AS department_ids "
                        "FROM contracts c WHERE file_code = :f"
                    ),
                    {"f": f"EXP-{tag}-{code}"},
                )
            )
            .mappings()
            .first()
        )
    await engine.dispose()
    return dict(row) if row else None


async def test_full_sync_pipeline(fake_socrata: FakeSocrata, scenario: dict[str, Any]) -> None:
    tag = scenario["tag"]
    fake_socrata.records = [
        _record(
            tag,
            code="A",
            subject="Servei de neteja d'edificis",
            denominacio_adjudicatari=f"Neteges Ràpides {tag} SL",
            identificacio_adjudicatari=f"B{tag.upper()[:7]}1",
            import_adjudicacio_sense="50000",
        ),
        _record(
            tag,
            code="B",
            subject="Manteniment de jardins",
            denominacio_adjudicatari=f"JARDINERIA ALIAS {tag}",
            identificacio_adjudicatari=f"B{tag.upper()[:7]}0",
        ),
    ]

    # ── Primer run: tot nou ────────────────────────────────────────────
    result = await _run_sync()
    assert result["new"] == 2
    assert result["failed"] == 0

    contract_a = await _contract(tag, "A")
    assert contract_a is not None
    assert contract_a["duration_months"] == 12
    assert str(contract_a["start_date"]) == "2026-01-16"
    # Regla 'neteja' → departament assignat.
    assert contract_a["department_ids"] == [scenario["dept_id"]]

    contract_b = await _contract(tag, "B")
    assert contract_b is not None
    # Àlies aplicat: contractor canònic, nom original conservat.
    assert contract_b["contractor_id"] == scenario["canonical_id"]
    assert contract_b["raw_contractor_name"] == f"JARDINERIA ALIAS {tag}"
    assert contract_b["department_ids"] is None  # cap regla no casa

    # ── Segon run: res no ha canviat + filtre incremental ─────────────
    result = await _run_sync()
    assert result["unchanged"] == 2
    assert result["new"] == 0
    last_where = fake_socrata.requests[-1].get("$where", "")
    assert "data_actualitzacio >=" in last_where  # incremental actiu

    # ── Tercer run: canvi d'import → updated + historial ──────────────
    fake_socrata.records[0]["import_adjudicacio_sense"] = "60000"
    result = await _run_sync()
    assert result["updated"] == 1
    assert result["unchanged"] == 1

    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    async with engine.connect() as conn:
        history = (
            await conn.execute(
                text(
                    "SELECT field, old_value, new_value FROM contract_history "
                    "WHERE contract_id = :c AND change_type = 'sync' "
                    "AND field = 'award_amount'"
                ),
                {"c": contract_a["id"]},
            )
        ).all()
    await engine.dispose()
    assert len(history) == 1
    assert history[0].old_value == "50000.00"
    assert history[0].new_value == "60000"

    # ── Duplicats per NIF: dos contractors amb el mateix NIF ──────────
    fake_socrata.records.append(
        _record(
            tag,
            code="C",
            subject="Neteja de platges",
            denominacio_adjudicatari=f"Neteges Repetides {tag} SCP",
            identificacio_adjudicatari=f"B{tag.upper()[:7]}1",  # mateix NIF que A
        )
    )
    result = await _run_sync(payload={"full": True})
    assert result["contractor_duplicates"] >= 1


async def test_corrupt_record_is_logged_and_run_is_partial(
    fake_socrata: FakeSocrata, scenario: dict[str, Any]
) -> None:
    tag = scenario["tag"]
    fake_socrata.records = [
        {"codi_ine10": INE10, "resultat": "Formalitzat"},  # sense codi_expedient
        _record(tag, code="OK", subject="Obres de vialitat"),
    ]

    result = await _run_sync()

    assert result["new"] == 1
    assert result["failed"] == 1

    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    async with engine.connect() as conn:
        run = (
            (
                await conn.execute(
                    text("SELECT status FROM sync_runs WHERE id = :i"),
                    {"i": result["sync_run_id"]},
                )
            )
            .mappings()
            .one()
        )
        items = (
            await conn.execute(
                text("SELECT count(*) FROM sync_item_logs WHERE sync_run_id = :i"),
                {"i": result["sync_run_id"]},
            )
        ).scalar_one()
    await engine.dispose()

    assert run["status"] == "partial"
    assert items == 1


async def test_disabled_connector_fails_with_clear_error(
    fake_socrata: FakeSocrata, scenario: dict[str, Any]
) -> None:
    async with session_factory() as session:
        await session.execute(text("UPDATE connectors SET enabled = false WHERE slug = 'socrata'"))
        await session.commit()

    from app.core.problems import Problem

    with pytest.raises(Problem) as excinfo:
        await _run_sync()

    assert excinfo.value.error_type == "connector-disabled"

    async with session_factory() as session:
        await session.execute(text("UPDATE connectors SET enabled = true WHERE slug = 'socrata'"))
        await session.commit()


async def test_phase_change_updates_row_by_id_intern(make_user) -> None:  # type: ignore[no-untyped-def]
    """El portal SUBSTITUEIX la fila quan la fase avança: amb id_intern
    estable, el canvi de fase actualitza la fila en lloc de duplicar-la
    (cas real 4732/2026)."""
    from uuid import uuid4

    from sqlalchemy import text

    from app.core.db import session_factory
    from app.integrations.socrata.sync import _upsert_record

    tag = uuid4().hex[:8]
    base = {
        "codi_expedient": f"DUP/{tag}",
        "id_intern": f"uuid-{tag}",
        "objecte_contracte": "Servei amb canvi de fase",
        "fase_publicacio": "Adjudicació",
        "resultat": "Adjudicació",
        "import_adjudicacio_sense": "1000",
    }
    async with session_factory() as session:
        assert await _upsert_record(session, dict(base), []) == "new"
        await session.commit()

    # La fase avança: mateixa fila a la font (mateix id_intern), estat nou.
    advanced = {
        **base,
        "fase_publicacio": "Formalització",
        "resultat": "Formalització",
        "data_formalitzacio_contracte": "2026-06-11T00:00:00.000",
    }
    async with session_factory() as session:
        assert await _upsert_record(session, dict(advanced), []) == "updated"
        await session.commit()

    async with session_factory() as session:
        rows = (
            await session.execute(
                text("SELECT id, status FROM contracts WHERE file_code = :f"),
                {"f": f"DUP/{tag}"},
            )
        ).all()
        history = (
            await session.execute(
                text(
                    "SELECT count(*) FROM contract_history ch JOIN contracts c "
                    "ON c.id = ch.contract_id WHERE c.file_code = :f AND ch.field = 'status'"
                ),
                {"f": f"DUP/{tag}"},
            )
        ).scalar_one()
        await session.execute(
            text("DELETE FROM contracts WHERE file_code = :f"), {"f": f"DUP/{tag}"}
        )
        await session.commit()
    assert len(rows) == 1  # cap duplicat
    assert rows[0].status == "Formalització"
    assert history == 1  # el canvi de fase queda historiat


async def test_manual_edits_survive_sync(api_client, make_user) -> None:  # type: ignore[no-untyped-def]
    """El manual mana (specs/contracts-api.md): un camp esmenat via PATCH
    queda protegit i la sincronització no el trepitja mai més."""
    from uuid import uuid4

    from sqlalchemy import text

    from app.core.db import session_factory
    from app.integrations.socrata.sync import _upsert_record
    from tests.conftest import login_headers

    tag = uuid4().hex[:8]
    record = {
        "codi_expedient": f"EDIT/{tag}",
        "id_intern": f"uuid-edit-{tag}",
        "objecte_contracte": "Servei amb data mal informada",
        "fase_publicacio": "Formalització",
        "resultat": "Formalització",
        "data_inici_execucio": "2026-01-01T00:00:00.000",
        "import_adjudicacio_sense": "1000",
    }
    async with session_factory() as session:
        assert await _upsert_record(session, dict(record), []) == "new"
        contract_id = (
            await session.execute(
                text("SELECT id FROM contracts WHERE file_code = :f"), {"f": f"EDIT/{tag}"}
            )
        ).scalar_one()
        await session.commit()

    # Esmena manual: la data d'inici bona és el 15, no l'1.
    admin = await make_user("admin")
    headers = login_headers(api_client, admin.email)
    patched = api_client.patch(
        f"/api/v1/contracts/{contract_id}",
        json={"start_date": "2026-01-15", "award_amount": "1234.56"},
        headers=headers,
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["start_date"] == "2026-01-15"

    # La font continua amb la dada dolenta i a més canvia una altra cosa.
    changed = {**record, "objecte_contracte": "Servei amb data mal informada (v2)"}
    async with session_factory() as session:
        assert await _upsert_record(session, dict(changed), []) == "updated"
        await session.commit()

    async with session_factory() as session:
        row = (
            await session.execute(
                text("SELECT start_date, award_amount, subject FROM contracts WHERE id = :id"),
                {"id": contract_id},
            )
        ).one()
        await session.execute(text("DELETE FROM contracts WHERE id = :id"), {"id": contract_id})
        await session.commit()
    assert str(row.start_date) == "2026-01-15"  # l'esmena sobreviu
    assert str(row.award_amount) == "1234.56"  # també l'import esmenat
    assert row.subject.endswith("(v2)")  # la resta segueix la font
