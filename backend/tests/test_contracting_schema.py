"""Tests d'esquema del nucli de contractació (migració 0004).

Verifiquen les restriccions crítiques amb dades reals; cada test reverteix
la seva transacció.
"""

from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings

CORE_TABLES = {
    "contractors",
    "contractor_aliases",
    "contractor_duplicates",
    "contracts",
    "contract_departments",
    "contract_managers",
    "extensions",
    "modifications",
    "award_criteria",
    "committee_members",
    "phase_documents",
    "contract_history",
    "duplicates",
    "association_rules",
    "minor_contracts",
    "minor_contract_departments",
    "sync_runs",
    "sync_item_logs",
    "cpv_codes",
}


@pytest.fixture
async def conn() -> AsyncIterator[AsyncConnection]:
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    async with engine.connect() as connection:
        yield connection
        await connection.rollback()
    await engine.dispose()


async def _insert_contract(
    conn: AsyncConnection, *, file_code: str, status: str = "Formalitzat", lot: str = ""
) -> int:
    result = await conn.execute(
        text(
            "INSERT INTO contracts (file_code, status, lot, subject) "
            "VALUES (:f, :s, :lot, 'Servei de neteja viària') RETURNING id"
        ),
        {"f": file_code, "s": status, "lot": lot},
    )
    return int(result.scalar_one())


async def test_core_tables_exist(conn: AsyncConnection) -> None:
    result = await conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))
    tables = {row[0] for row in result}

    assert CORE_TABLES <= tables


async def test_contract_natural_key_unique(conn: AsyncConnection) -> None:
    file_code = f"EXP-{uuid4().hex[:8]}"
    await _insert_contract(conn, file_code=file_code)

    # Lot diferent: permès (la clau natural inclou el lot).
    await _insert_contract(conn, file_code=file_code, lot="2")

    with pytest.raises(IntegrityError):
        await _insert_contract(conn, file_code=file_code)
    await conn.rollback()


async def test_extension_number_unique_per_contract(conn: AsyncConnection) -> None:
    contract_id = await _insert_contract(conn, file_code=f"EXP-{uuid4().hex[:8]}")
    await conn.execute(
        text("INSERT INTO extensions (contract_id, number) VALUES (:c, 1)"),
        {"c": contract_id},
    )

    with pytest.raises(IntegrityError):
        await conn.execute(
            text("INSERT INTO extensions (contract_id, number) VALUES (:c, 1)"),
            {"c": contract_id},
        )
    await conn.rollback()


async def test_duplicate_pair_must_be_ordered_and_unique(conn: AsyncConnection) -> None:
    first = await _insert_contract(conn, file_code=f"EXP-{uuid4().hex[:8]}")
    second = await _insert_contract(conn, file_code=f"EXP-{uuid4().hex[:8]}")
    low, high = sorted([first, second])

    await conn.execute(
        text("INSERT INTO duplicates (contract_id_1, contract_id_2) VALUES (:a, :b)"),
        {"a": low, "b": high},
    )

    # Ordre invers: el CHECK el rebutja (mai el mateix parell en dos ordres).
    with pytest.raises(DBAPIError):
        await conn.execute(
            text("INSERT INTO duplicates (contract_id_1, contract_id_2) VALUES (:a, :b)"),
            {"a": high, "b": low},
        )
    await conn.rollback()


async def test_trigram_search_on_subject(conn: AsyncConnection) -> None:
    file_code = f"EXP-{uuid4().hex[:8]}"
    await _insert_contract(conn, file_code=file_code)

    result = await conn.execute(
        text("SELECT file_code FROM contracts WHERE subject % 'neteja viaria' AND file_code = :f"),
        {"f": file_code},
    )

    assert result.scalar_one_or_none() == file_code


async def test_contracts_updated_at_trigger(conn: AsyncConnection) -> None:
    contract_id = await _insert_contract(conn, file_code=f"EXP-{uuid4().hex[:8]}")
    before = (
        await conn.execute(
            text("SELECT updated_at FROM contracts WHERE id = :id"), {"id": contract_id}
        )
    ).scalar_one()

    await conn.execute(
        text("UPDATE contracts SET subject = 'Canviat' WHERE id = :id"), {"id": contract_id}
    )
    after = (
        await conn.execute(
            text("SELECT updated_at FROM contracts WHERE id = :id"), {"id": contract_id}
        )
    ).scalar_one()

    assert after > before


async def test_contractor_alias_unique(conn: AsyncConnection) -> None:
    contractor_id = (
        await conn.execute(
            text(
                "INSERT INTO contractors (canonical_name, tax_id) "
                "VALUES ('Empresa de Prova SL', :nif) RETURNING id"
            ),
            {"nif": f"B{uuid4().hex[:8].upper()}"},
        )
    ).scalar_one()
    alias = f"EMPRESA PROVA {uuid4().hex[:6]}"
    await conn.execute(
        text("INSERT INTO contractor_aliases (alias, contractor_id) VALUES (:a, :c)"),
        {"a": alias, "c": contractor_id},
    )

    with pytest.raises(IntegrityError):
        await conn.execute(
            text("INSERT INTO contractor_aliases (alias, contractor_id) VALUES (:a, :c)"),
            {"a": alias, "c": contractor_id},
        )
    await conn.rollback()
