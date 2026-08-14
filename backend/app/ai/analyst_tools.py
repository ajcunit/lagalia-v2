"""Eines tancades de l'analista (specs/ai-analyst.md). Mai SQL lliure:
consultes fixes amb paràmetres vinculats i límits durs."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.contracts import risk_audit


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def search_contracts(session: AsyncSession, args: dict[str, Any]) -> list[dict[str, Any]]:
    conditions, params = ["1=1"], {}
    if args.get("q"):
        conditions.append(
            "(subject ILIKE :q ESCAPE '\\' OR file_code ILIKE :q ESCAPE '\\')"
        )
        params["q"] = f"%{_escape_like(str(args['q'])[:100])}%"
    if args.get("year"):
        conditions.append("EXTRACT(year FROM published_at) = :year")
        params["year"] = int(args["year"])
    if args.get("contract_type"):
        conditions.append("contract_type ILIKE :ct ESCAPE '\\'")
        params["ct"] = f"%{_escape_like(str(args['contract_type'])[:50])}%"
    limit = min(int(args.get("limit") or 10), 10)
    rows = (
        await session.execute(
            text(
                "SELECT file_code, subject, contract_type, "  # noqa: S608
                "award_amount, published_at "
                # Les condicions són literals fixos del codi; els valors
                # de l'usuari SEMPRE van per paràmetres vinculats.
                f"FROM contracts WHERE {' AND '.join(conditions)} "
                "ORDER BY published_at DESC NULLS LAST LIMIT :lim"
            ),
            {**params, "lim": limit},
        )
    ).all()
    return [dict(r._mapping) for r in rows]


_GROUPS = {
    "year": "EXTRACT(year FROM published_at)",
    "contract_type": "contract_type",
    "department": "awarding_department",
    "contractor": "(SELECT canonical_name FROM contractors WHERE id = contractor_id)",
}
_METRICS = {"count": "count(*)", "sum_award": "sum(award_amount)"}


async def aggregate(session: AsyncSession, args: dict[str, Any]) -> list[dict[str, Any]]:
    group_sql = _GROUPS.get(str(args.get("group_by")))
    metric_sql = _METRICS.get(str(args.get("metric") or "count"))
    if group_sql is None or metric_sql is None:
        return [{"error": f"group_by vàlids: {sorted(_GROUPS)}; metric: {sorted(_METRICS)}"}]
    conditions, params = ["1=1"], {}
    if args.get("year_from"):
        conditions.append("EXTRACT(year FROM published_at) >= :yf")
        params["yf"] = int(args["year_from"])
    if args.get("year_to"):
        conditions.append("EXTRACT(year FROM published_at) <= :yt")
        params["yt"] = int(args["year_to"])
    rows = (
        await session.execute(
            text(
                f"SELECT {group_sql} AS grup, "  # noqa: S608
                f"{metric_sql} AS valor "
                # group_sql/metric_sql surten d'un diccionari tancat (whitelist);
                # els valors de l'usuari van per paràmetres vinculats.
                f"FROM contracts WHERE {' AND '.join(conditions)} "
                "GROUP BY 1 ORDER BY 2 DESC NULLS LAST LIMIT 20"
            ),
            params,
        )
    ).all()
    return [dict(r._mapping) for r in rows]


async def get_red_flags(session: AsyncSession, args: dict[str, Any]) -> dict[str, Any]:
    today = datetime.now(UTC).date()
    return {
        "possibles_fraccionaments": _trim(await risk_audit._splitting(session, today)),
        "baixes_temeraries": _trim(await risk_audit._reckless_bids(session)),
        "renovacions_critiques": _trim(await risk_audit._critical_renewals(session, today)),
        "falta_concurrencia": _trim(await risk_audit._single_bidder(session)),
    }


def _trim(block: dict[str, Any]) -> dict[str, Any]:
    return {"total": block["total"], "top": block["items"][:3]}


async def totals(session: AsyncSession, args: dict[str, Any]) -> dict[str, Any]:
    row = (
        await session.execute(
            text(
                "SELECT (SELECT count(*) FROM contracts) AS contracts, "
                "(SELECT count(*) FROM minor_contracts) AS minor_contracts, "
                "(SELECT count(*) FROM contractors) AS contractors, "
                "(SELECT sum(award_amount) FROM contracts) AS total_awarded, "
                "(SELECT sum(award_amount) FROM minor_contracts) AS total_minor_awarded"
            )
        )
    ).one()
    return dict(row._mapping)


TOOLS = {
    "search_contracts": (
        search_contracts,
        "Cerca contractes per text/any/tipus. Args: q?, year?, contract_type?, limit?≤10",
    ),
    "aggregate": (
        aggregate,
        "Agrega contractes. Args: group_by (year|contract_type|department|contractor), "
        "metric (count|sum_award), year_from?, year_to?",
    ),
    "get_red_flags": (get_red_flags, "Red flags actuals (totals + top 3 per bloc). Sense args."),
    "totals": (totals, "Comptadors i imports globals de l'ens. Sense args."),
}
