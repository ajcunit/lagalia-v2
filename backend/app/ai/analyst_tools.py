"""Eines tancades de l'analista (specs/ai-analyst.md). Mai SQL lliure:
consultes fixes amb paràmetres vinculats i límits durs."""

import re
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.contracts import risk_audit


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _scope_condition(args: dict[str, Any], params: dict[str, Any]) -> str:
    """Abast departamental de qui pregunta (specs/ai-analyst.md): els usuaris
    amb abast «departments» NOMÉS veuen contractes dels seus departaments."""
    scope = args.get("_scope")
    if scope is None or getattr(scope, "type", "all") == "all":
        return "1=1"
    params["_scope_deps"] = list(getattr(scope, "department_ids", None) or [])
    return (
        "id IN (SELECT contract_id FROM contract_departments "
        "WHERE department_id = ANY(:_scope_deps))"
    )


def _is_scoped(args: dict[str, Any]) -> bool:
    scope = args.get("_scope")
    return scope is not None and getattr(scope, "type", "all") != "all"


async def search_contracts(session: AsyncSession, args: dict[str, Any]) -> list[dict[str, Any]]:
    conditions, params = [], {}
    conditions.append(_scope_condition(args, params))
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
    conditions, params = [], {}
    conditions.append(_scope_condition(args, params))
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
    if _is_scoped(args):
        return {
            "error": "Les red flags són una anàlisi de tot l'ens: només disponibles "
            "amb abast global. Aquest usuari té abast departamental."
        }
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
    if _is_scoped(args):
        params: dict[str, Any] = {}
        condition = _scope_condition(args, params)
        row = (
            await session.execute(
                text(
                    "SELECT count(*) AS contracts, "  # noqa: S608 — literal fix
                    f"sum(award_amount) AS total_awarded FROM contracts WHERE {condition}"
                ),
                params,
            )
        ).one()
        return {
            **dict(row._mapping),
            "nota": "abast departamental: només els contractes dels teus departaments",
        }
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


# ── Accés obert de NOMÉS LECTURA a dades i metadades (specs/ai-analyst.md) ──
# Whitelist explícita: taules de negoci i metadades operatives. MAI usuaris,
# sessions, credencials, paràmetres, xats ni auditoria de seguretat.
# NOMÉS dades de contractes i d'adjudicataris (petició de l'Esteve,
# 2026-08-18) + referència CPV i departaments (necessaris per anomenar-los).
QUERYABLE_TABLES = (
    "contracts",
    "minor_contracts",
    "contractors",
    "contractor_aliases",
    "extensions",
    "modifications",
    "contract_executions",
    "phase_documents",
    "award_criteria",
    "committee_members",
    "contract_departments",
    "departments",
    "contract_history",
    "cpv_codes",
)

_FORBIDDEN_KEYWORDS = re.compile(
    r"\b(insert|update|delete|drop|alter|create|grant|revoke|truncate|copy|call|do|"
    r"vacuum|analyze|set|reset|listen|notify|refresh|comment|security|pg_sleep)\b",
    re.IGNORECASE,
)
_SENSITIVE_IDENTIFIERS = re.compile(
    r"\b(users|sessions|connector_credentials|service_accounts|settings|"
    r"chat_threads|chat_messages|audit_log|ai_provider_profiles|api_keys|"
    r"pg_catalog|pg_shadow|pg_authid|information_schema)\b",
    re.IGNORECASE,
)


def validate_select(sql: str) -> str:
    """Validació dura d'una consulta lliure: un únic SELECT sobre la whitelist.

    A més de la validació, l'execució va dins d'una transacció READ ONLY amb
    statement_timeout: encara que alguna cosa s'escapés, no pot escriure.
    """
    cleaned = sql.strip().rstrip(";").strip()
    if ";" in cleaned:
        raise ValueError("només s'admet una única sentència")
    if "--" in cleaned or "/*" in cleaned:
        raise ValueError("no s'admeten comentaris SQL")
    if not re.match(r"^select\b", cleaned, re.IGNORECASE):
        raise ValueError("només s'admeten consultes SELECT")
    if _FORBIDDEN_KEYWORDS.search(cleaned):
        raise ValueError("la consulta conté paraules clau no permeses")
    if _SENSITIVE_IDENTIFIERS.search(cleaned):
        raise ValueError("la consulta toca taules no permeses")
    referenced = {
        m.group(2).lower()
        for m in re.finditer(r"\b(from|join)\s+([a-zA-Z_][a-zA-Z0-9_]*)", cleaned, re.IGNORECASE)
    }
    unknown = referenced - set(QUERYABLE_TABLES)
    if unknown:
        raise ValueError(
            f"taules fora de la whitelist: {sorted(unknown)}; "
            f"permeses: {', '.join(QUERYABLE_TABLES)}"
        )
    if not referenced:
        raise ValueError("la consulta ha de llegir d'alguna taula permesa")
    return cleaned


async def data_schema(session: AsyncSession, args: dict[str, Any]) -> list[dict[str, Any]]:
    """Catàleg de taules i columnes consultables (metadades del model)."""
    if _is_scoped(args):
        return [
            {
                "error": "El catàleg i la consulta lliure només estan disponibles "
                "amb abast global."
            }
        ]
    rows = (
        await session.execute(
            text(
                "SELECT table_name, column_name, data_type FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = ANY(:tables) "
                "ORDER BY table_name, ordinal_position"
            ),
            {"tables": list(QUERYABLE_TABLES)},
        )
    ).all()
    tables: dict[str, list[str]] = {}
    for row in rows:
        tables.setdefault(row.table_name, []).append(f"{row.column_name} ({row.data_type})")
    return [{"table": name, "columns": columns} for name, columns in tables.items()]


async def sql_select(session: AsyncSession, args: dict[str, Any]) -> list[dict[str, Any]]:
    """Consulta SELECT lliure validada, en transacció de només lectura.

    Només per a usuaris amb abast GLOBAL: amb SQL lliure no es pot garantir
    el filtre departamental, així que als usuaris amb abast restringit se'ls
    denega i s'els redirigeix a les eines tancades (que sí que filtren).
    """
    if _is_scoped(args):
        return [
            {
                "error": "Consulta lliure no disponible: aquest usuari té abast "
                "departamental. Fes servir search_contracts/aggregate/totals, "
                "que filtren automàticament al seu abast."
            }
        ]
    raw = str(args.get("sql") or "")
    validated = validate_select(raw)
    from app.core.db import session_factory

    async with session_factory() as read_session:
        await read_session.execute(text("SET TRANSACTION READ ONLY"))
        await read_session.execute(text("SET LOCAL statement_timeout = '5s'"))
        result = await read_session.execute(
            text(f"SELECT * FROM ({validated}) AS consulta LIMIT 200")  # noqa: S608 — validat
        )
        rows = result.mappings().all()
        await read_session.rollback()
    return [dict(row) for row in rows]


TOOLS.update(
    {
        "data_schema": (
            data_schema,
            "Catàleg de totes les taules i columnes consultables (metadades). Sense args.",
        ),
        "sql_select": (
            sql_select,
            "Consulta SQL lliure de NOMÉS lectura sobre les taules del catàleg "
            "(un únic SELECT; màx. 200 files). Args: sql. Consulta primer data_schema "
            "si no coneixes les columnes.",
        ),
    }
)


async def help_articles(session: AsyncSession, args: dict[str, Any]) -> list[dict[str, Any]]:
    """Wiki d'ajuda de la plataforma (specs/help-wiki.md): manual d'usuari.

    Sempre l'audiència general — els articles d'administració no passen mai
    pel xat (l'assistent el poden usar rols que no són admin).
    """
    from app.modules.help.articles import visible_articles

    query = str(args.get("q") or "").strip().casefold()
    articles = visible_articles(is_admin=False)
    if query:
        terms = [term for term in query.split() if len(term) > 2]
        scored = []
        for article in articles:
            haystack = f"{article.title}\n{article.body}".casefold()
            score = sum(haystack.count(term) for term in terms)
            if score:
                scored.append((score, article))
        articles = [a for _, a in sorted(scored, key=lambda pair: -pair[0])]
    return [
        {"title": a.title, "slug": a.slug, "content": a.body[:2000]}
        for a in articles[:3]
    ]


TOOLS["help_articles"] = (
    help_articles,
    "Manual d'ús de LAGALia (wiki d'ajuda): com funciona cada pantalla o "
    "funcionalitat. Args: q (paraules clau). Usa'l quan preguntin com fer "
    "servir la plataforma, no per a dades.",
)
