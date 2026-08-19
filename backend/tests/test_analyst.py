"""Eines de l'analista i del xat general (specs/ai-analyst.md)."""

import pytest

pytestmark = pytest.mark.anyio


def test_sql_select_validation() -> None:
    """Validació dura de la consulta lliure (specs/ai-analyst.md)."""
    import pytest as _pytest

    from app.ai.analyst_tools import validate_select

    # Vàlida: SELECT únic sobre taules de la whitelist.
    ok = validate_select("SELECT file_code, award_amount FROM contracts LIMIT 5;")
    assert ok.lower().startswith("select")

    for bad in (
        "UPDATE contracts SET status = 'x'",
        "SELECT 1; DROP TABLE contracts",
        "SELECT * FROM users",
        "SELECT * FROM chat_messages",
        "SELECT * FROM contracts -- comentari",
        "WITH x AS (SELECT 1) SELECT * FROM x",
        "SELECT pg_sleep(10) FROM contracts",
        "SELECT * FROM pg_catalog.pg_tables",
        "SELECT 1",
    ):
        with _pytest.raises(ValueError):
            validate_select(bad)


async def test_sql_select_readonly_and_schema(api_client, make_user) -> None:  # type: ignore[no-untyped-def]
    from uuid import uuid4

    from sqlalchemy import text as sql_text

    from app.ai.analyst_tools import data_schema, sql_select
    from app.core.db import session_factory

    tag = uuid4().hex[:8]
    async with session_factory() as session:
        await session.execute(
            sql_text(
                "INSERT INTO contracts (file_code, status, lot, subject, award_amount) "
                "VALUES (:f, 'Formalització', '', 'Consulta lliure', 1234)"
            ),
            {"f": f"SQL/{tag}"},
        )
        await session.commit()

    async with session_factory() as session:
        rows = await sql_select(
            session,
            {"sql": f"SELECT file_code, award_amount FROM contracts WHERE file_code = 'SQL/{tag}'"},  # noqa: S608
        )
        assert rows and str(rows[0]["award_amount"]).startswith("1234")

        schema = await data_schema(session, {})
        tables = {entry["table"] for entry in schema}
        assert "contracts" in tables and "extensions" in tables
        # Fora de l'àmbit contractes/adjudicataris i taules sensibles: mai.
        assert "sync_runs" not in tables and "users" not in tables

    async with session_factory() as session:
        await session.execute(
            sql_text("DELETE FROM contracts WHERE file_code = :f"), {"f": f"SQL/{tag}"}
        )
        await session.commit()


async def test_tools_respect_departmental_scope(api_client, make_user) -> None:  # type: ignore[no-untyped-def]
    """Petició de l'Esteve (2026-08-18): el xat/analista només pot donar
    informació dins de l'abast de qui pregunta."""
    from uuid import uuid4

    from sqlalchemy import text as sql_text

    from app.ai.analyst_tools import data_schema, search_contracts, sql_select, totals
    from app.core.authz import ScopeInfo
    from app.core.db import session_factory

    tag = uuid4().hex[:8]
    async with session_factory() as session:
        dept_a = (
            await session.execute(
                sql_text("INSERT INTO departments (code, name) VALUES (:c, 'ScopeA') RETURNING id"),
                {"c": f"SA-{tag}"},
            )
        ).scalar_one()
        dept_b = (
            await session.execute(
                sql_text("INSERT INTO departments (code, name) VALUES (:c, 'ScopeB') RETURNING id"),
                {"c": f"SB-{tag}"},
            )
        ).scalar_one()
        mine = (
            await session.execute(
                sql_text(
                    "INSERT INTO contracts (file_code, status, lot, subject) "
                    "VALUES (:f, 'Formalització', '', 'Contracte del meu departament') RETURNING id"
                ),
                {"f": f"SCP-A/{tag}"},
            )
        ).scalar_one()
        other = (
            await session.execute(
                sql_text(
                    "INSERT INTO contracts (file_code, status, lot, subject) "
                    "VALUES (:f, 'Formalització', '', 'Contracte aliè') RETURNING id"
                ),
                {"f": f"SCP-B/{tag}"},
            )
        ).scalar_one()
        await session.execute(
            sql_text(
                "INSERT INTO contract_departments (contract_id, department_id) VALUES (:c, :d)"
            ),
            {"c": mine, "d": dept_a},
        )
        await session.execute(
            sql_text(
                "INSERT INTO contract_departments (contract_id, department_id) VALUES (:c, :d)"
            ),
            {"c": other, "d": dept_b},
        )
        await session.commit()

    scoped = ScopeInfo(type="departments", department_ids=[dept_a])

    async with session_factory() as session:
        # SQL lliure i catàleg: denegats amb abast departamental.
        denied = await sql_select(
            session, {"sql": "SELECT count(*) FROM contracts", "_scope": scoped}
        )
        assert "error" in denied[0]
        assert "error" in (await data_schema(session, {"_scope": scoped}))[0]

        # La cerca tancada NOMÉS retorna el contracte del seu departament.
        rows = await search_contracts(session, {"q": tag, "_scope": scoped})
        codes = {row["file_code"] for row in rows}
        assert codes == {f"SCP-A/{tag}"}

        # Els totals van amb nota i només compten el seu abast.
        scoped_totals = await totals(session, {"_scope": scoped})
        assert scoped_totals["contracts"] == 1
        assert "nota" in scoped_totals

        # Amb abast global tot hi és.
        all_rows = await search_contracts(session, {"q": tag, "_scope": ScopeInfo(type="all")})
        assert {row["file_code"] for row in all_rows} == {f"SCP-A/{tag}", f"SCP-B/{tag}"}

    async with session_factory() as session:
        await session.execute(
            sql_text("DELETE FROM contracts WHERE id IN (:a, :b)"), {"a": mine, "b": other}
        )
        await session.execute(
            sql_text("DELETE FROM departments WHERE id IN (:a, :b)"), {"a": dept_a, "b": dept_b}
        )
        await session.commit()
