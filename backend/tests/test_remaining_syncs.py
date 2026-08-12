"""Syncs de pròrrogues, menors i CPV (BD real, Socrata simulat)."""

from collections.abc import AsyncIterator, Awaitable, Callable
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
from app.integrations.socrata.sync_common import classify_situacio
from app.integrations.socrata.sync_cpv import levels_from_row, sync_cpv
from app.integrations.socrata.sync_rpc import (
    merge_minor_records,
    sync_extensions,
    sync_minor_contracts,
)
from app.jobs.registry import JobContext

INE10 = "4305160009"


# ─────────────────────────────── unitats pures ───────────────────────────────


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("pròrroga", "extension"),
        ("PRORROGA", "extension"),
        ("Modificació", "modification"),
        ("modificacio de contracte", "modification"),
        ("liquidació", "settlement"),
        ("LIQUIDACIO", "settlement"),
        ("menor", "minor_award"),
        ("adjudicació", "other"),
        (None, "other"),
    ],
)
def test_classify_situacio(value: str | None, expected: str) -> None:
    assert classify_situacio(value) == expected


def test_merge_minor_records_award_and_settlement() -> None:
    group = [
        {
            "situaci_contractual": "menor",
            "contracte": "Compra de material",
            "tipus_contracte": "Subministraments",
            "import_adjudicacio": "500.50",
            "data_adjudicacio": "2025-03-01T00:00:00.000",
            "exercici": "2025",
            "anys_durada": "0",
            "mesos_durada": "1",
            "dies_durada": "0",
            "adjudicatari": "Proveïdor SL",
        },
        {
            "situaci_contractual": "liquidació",
            "contracte": "Compra de material",
            "import_liquidacio": "480",
            "data_liquidacio": "2025-06-01T00:00:00.000",
            "tipus_liquidacio": "Total",
            "exercici": "2025",
        },
    ]

    merged = merge_minor_records("100/2025", group)

    assert merged is not None
    assert merged["description"] == "Compra de material"
    assert str(merged["award_amount"]) == "500.50"
    assert str(merged["settlement_amount"]) == "480"
    assert merged["settlement_type"] == "Total"
    assert merged["fiscal_year"] == 2025
    assert merged["_contractor_name"] == "Proveïdor SL"
    assert merged["raw_award"] is group[0]
    assert merged["raw_settlement"] is group[1]


def test_merge_minor_settlement_only_still_creates_row() -> None:
    merged = merge_minor_records(
        "200/2025",
        [{"situaci_contractual": "liquidació", "contracte": "X", "import_liquidacio": "5"}],
    )

    assert merged is not None
    assert merged["award_amount"] is None
    assert str(merged["settlement_amount"]) == "5"


def test_cpv_levels_from_row() -> None:
    row = {
        "cpv_divisi": "03000000-1",
        "descripci_divisi": "Agricultura",
        "cpv_grup": "03100000-2",
        "descripci_grup": "Productes agrícoles",
        "cpv_classe": "03110000-5",
        "descripci_classe": "Cultius",
        "cpv_categoria": "03111000-2",
        "descripci_categoria": "Llavors",
    }

    levels = levels_from_row(row)

    assert [(entry["code"], entry["parent_code"]) for entry in levels] == [
        ("03000000-1", None),
        ("03100000-2", "03000000-1"),
        ("03110000-5", "03100000-2"),
        ("03111000-2", "03110000-5"),
    ]


# ─────────────────────────────── e2e simulats ───────────────────────────────


class FakeSocrata:
    def __init__(self) -> None:
        self.datasets: dict[str, list[dict[str, Any]]] = {}

    def handler(self, request: httpx.Request) -> httpx.Response:
        dataset = request.url.path.rsplit("/", 1)[-1].removesuffix(".json")
        params = dict(request.url.params)
        rows = self.datasets.get(dataset, [])
        where = params.get("$where", "")
        if "procediment_adjudicacio = 'Menor'" in where:
            rows = [r for r in rows if r.get("procediment_adjudicacio") == "Menor"]
        offset = int(params.get("$offset", 0))
        limit = int(params.get("$limit", 1000))
        return httpx.Response(200, json=rows[offset : offset + limit])


@pytest.fixture
async def fake_rpc(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[FakeSocrata]:
    fake = FakeSocrata()
    monkeypatch.setattr(
        SocrataConnector,
        "client",
        lambda self: SocrataClient(
            "https://fake.socrata.test",
            min_interval_seconds=0,
            transport=httpx.MockTransport(fake.handler),
        ),
    )
    created_setting = False
    async with session_factory() as session:
        record = await hub.ensure_registered(session, "socrata")
        was_enabled = record.enabled
        record.enabled = True
        existing = (
            await session.execute(text("SELECT id FROM settings WHERE key = 'org.ine10_code'"))
        ).scalar_one_or_none()
        if existing is None:
            await session.execute(
                text("INSERT INTO settings (key, value) VALUES ('org.ine10_code', :v)"),
                {"v": f'"{INE10}"'},
            )
            created_setting = True
        await session.commit()

    yield fake

    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    async with engine.begin() as conn:
        if created_setting:
            await conn.execute(text("DELETE FROM settings WHERE key = 'org.ine10_code'"))
        if not was_enabled:
            await conn.execute(text("UPDATE connectors SET enabled = false WHERE slug = 'socrata'"))
        await conn.execute(
            text(
                "DELETE FROM sync_item_logs WHERE sync_run_id IN "
                "(SELECT id FROM sync_runs WHERE endpoint LIKE '%fake.socrata.test%')"
            )
        )
        await conn.execute(text("DELETE FROM sync_runs WHERE endpoint LIKE '%fake.socrata.test%'"))
    await engine.dispose()


async def _run(
    handler: "Callable[[JobContext], Awaitable[dict[str, Any] | None]]",
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    async def _noop(_pct: int, _msg: str | None = None) -> None:
        return None

    result = await handler(JobContext(job_id=uuid4(), payload=payload, set_progress=_noop))
    assert result is not None
    return result


@pytest.fixture
async def contract_rows() -> AsyncIterator[dict[str, Any]]:
    tag = uuid4().hex[:8]
    file_code = f"PRG-{tag}/2024"
    ids = []
    async with session_factory() as session:
        for lot in ("", "2"):
            row_id = (
                await session.execute(
                    text(
                        "INSERT INTO contracts (file_code, status, lot, subject, "
                        "calculated_end_date) VALUES (:f, 'Formalitzat', :lot, 'Servei', "
                        "'2025-12-31') RETURNING id"
                    ),
                    {"f": file_code, "lot": lot},
                )
            ).scalar_one()
            ids.append(row_id)
        await session.commit()

    yield {"tag": tag, "file_code": file_code, "ids": ids}

    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM contracts WHERE file_code = :f"), {"f": file_code})
    await engine.dispose()


async def test_sync_extensions_end_to_end(
    fake_rpc: FakeSocrata, contract_rows: dict[str, Any]
) -> None:
    file_code = contract_rows["file_code"]
    fake_rpc.datasets["hb6v-jcbf"] = [
        {
            "codi_expedient": file_code,
            "situaci_contractual": "pròrroga",
            "numero_prorroga": "1",
            "data_inici_prorroga": "2026-01-01T00:00:00.000",
            "data_fi_prorroga": "2026-12-31T00:00:00.000",
            "import_adjudicacio": "1000",
            "exercici": "2026",
        },
        {
            "codi_expedient": "INEXISTENT/999",
            "situaci_contractual": "pròrroga",
            "numero_prorroga": "1",
        },
        {"codi_expedient": file_code, "situaci_contractual": "menor"},  # s'ignora
    ]

    result = await _run(sync_extensions)

    assert result["new"] == 1
    assert result["unmatched"] == 1

    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    async with engine.connect() as conn:
        extension = (
            (
                await conn.execute(
                    text(
                        "SELECT contract_id, number, end_date FROM extensions "
                        "WHERE contract_id = ANY(:ids)"
                    ),
                    {"ids": contract_rows["ids"]},
                )
            )
            .mappings()
            .all()
        )
        # Propagació a TOTES les files de l'expedient.
        end_dates = (
            await conn.execute(
                text("SELECT calculated_end_date FROM contracts WHERE file_code = :f"),
                {"f": file_code},
            )
        ).scalars()
        history = (
            await conn.execute(
                text(
                    "SELECT count(*) FROM contract_history WHERE contract_id = ANY(:ids) "
                    "AND field = 'calculated_end_date' AND change_type = 'sync'"
                ),
                {"ids": contract_rows["ids"]},
            )
        ).scalar_one()
    await engine.dispose()

    assert len(extension) == 1
    assert extension[0]["number"] == 1
    assert str(extension[0]["end_date"]) == "2026-12-31"
    assert [str(d) for d in end_dates] == ["2026-12-31", "2026-12-31"]
    assert history == 2

    # Re-run: sense canvis.
    result = await _run(sync_extensions)
    assert result["unchanged"] == 1


async def test_sync_minor_contracts_end_to_end(fake_rpc: FakeSocrata) -> None:
    tag = uuid4().hex[:8]
    file_code = f"MEN-{tag}/2025"
    award = {
        "codi_expedient": file_code,
        "procediment_adjudicacio": "Menor",
        "situaci_contractual": "menor",
        "contracte": "Compra de cadires",
        "tipus_contracte": "Subministraments",
        "import_adjudicacio": "900",
        "data_adjudicacio": "2025-02-01T00:00:00.000",
        "exercici": "2025",
        "adjudicatari": f"Mobles {tag} SL",
    }
    settlement = {
        "codi_expedient": file_code,
        "procediment_adjudicacio": "Menor",
        "situaci_contractual": "liquidació",
        "import_liquidacio": "900",
        "data_liquidacio": "2025-05-01T00:00:00.000",
        "tipus_liquidacio": "Total",
        "exercici": "2025",
    }
    fake_rpc.datasets["hb6v-jcbf"] = [award, settlement]

    try:
        result = await _run(sync_minor_contracts)
        assert result["new"] == 1

        engine = create_async_engine(settings.database_url, poolclass=NullPool)
        async with engine.connect() as conn:
            row = (
                (
                    await conn.execute(
                        text(
                            "SELECT description, award_amount, settlement_amount, "
                            "contractor_id FROM minor_contracts WHERE file_code = :f"
                        ),
                        {"f": file_code},
                    )
                )
                .mappings()
                .one()
            )
        await engine.dispose()
        assert row["description"] == "Compra de cadires"
        assert str(row["award_amount"]) == "900.00"
        assert str(row["settlement_amount"]) == "900.00"
        assert row["contractor_id"] is not None

        # Re-run: unchanged; canvi d'import: updated.
        result = await _run(sync_minor_contracts)
        assert result["unchanged"] == 1
        award["import_adjudicacio"] = "950"
        result = await _run(sync_minor_contracts)
        assert result["updated"] == 1
    finally:
        engine = create_async_engine(settings.database_url, poolclass=NullPool)
        async with engine.begin() as conn:
            await conn.execute(
                text("DELETE FROM minor_contracts WHERE file_code = :f"), {"f": file_code}
            )
            await conn.execute(
                text("DELETE FROM contractors WHERE canonical_name LIKE :p"),
                {"p": f"%{tag}%"},
            )
        await engine.dispose()


async def test_sync_cpv_end_to_end(fake_rpc: FakeSocrata) -> None:
    fake_rpc.datasets["wxdw-5eyv"] = [
        {
            "cpv_divisi": "98000000-3",
            "descripci_divisi": "Altres serveis",
            "cpv_grup": "98300000-6",
            "descripci_grup": "Serveis diversos",
            "cpv_classe": "98310000-9",
            "descripci_classe": "Bugaderia",
            "cpv_categoria": "98311000-6",
            "descripci_categoria": "Recollida de roba",
        },
        {
            "cpv_divisi": "98000000-3",
            "descripci_divisi": "Altres serveis",
            "cpv_grup": "98300000-6",
            "descripci_grup": "Serveis diversos",
            "cpv_classe": "98310000-9",
            "descripci_classe": "Bugaderia",
            "cpv_categoria": "98312000-3",
            "descripci_categoria": "Neteja de tèxtils",
        },
    ]

    try:
        result = await _run(sync_cpv)
        assert result["new"] == 5  # 1 divisió + 1 grup + 1 classe + 2 categories

        engine = create_async_engine(settings.database_url, poolclass=NullPool)
        async with engine.connect() as conn:
            parents = (
                (
                    await conn.execute(
                        text(
                            "SELECT code, parent_code, level FROM cpv_codes "
                            "WHERE code LIKE '983%' OR code = '98000000-3' ORDER BY code"
                        )
                    )
                )
                .mappings()
                .all()
            )
        await engine.dispose()
        by_code = {r["code"]: r for r in parents}
        assert by_code["98300000-6"]["parent_code"] == "98000000-3"
        assert by_code["98311000-6"]["parent_code"] == "98310000-9"
        assert by_code["98311000-6"]["level"] == "Category"

        result = await _run(sync_cpv)
        assert result["unchanged"] == 5
    finally:
        engine = create_async_engine(settings.database_url, poolclass=NullPool)
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "DELETE FROM cpv_codes WHERE code IN "
                    "('98000000-3','98300000-6','98310000-9','98311000-6','98312000-3')"
                )
            )
        await engine.dispose()
