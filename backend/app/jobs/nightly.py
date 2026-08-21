"""Cadena nocturna de sincronització (specs/sync-schedule.md).

Executa les sincros de dades en ordre i en sèrie reutilitzant els
handlers registrats: l'ordre importa (extensions i execució depenen dels
contractes acabats de sincronitzar). Un pas que falla no atura la resta.
"""

import json
from datetime import datetime, time
from typing import Any
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs.registry import JobContext, get_handler, job

logger = structlog.get_logger()

TIMEZONE = ZoneInfo("Europe/Madrid")

# Ordre prescrit a docs/08 §3: extensions encadenades després de contracts.
# alerts.recompute tanca la cadena: els indicadors de venciment es calculen
# sobre les dades acabades de sincronitzar (cas real: a producció no
# s'omplien mai perquè cap productor encuava el job).
NIGHTLY_STEPS = [
    "sync.contracts",
    "sync.extensions",
    "sync.minor_contracts",
    "sync.execution",
    "alerts.recompute",
]

SETTING_ENABLED = "sync.nightly_enabled"
SETTING_TIME = "sync.nightly_time"
SETTING_DAYS = "sync.nightly_days"
SETTING_ENRICH = "sync.nightly_enrich"

_DEFAULT_TIME = "02:30"


@job("sync.nightly")
async def sync_nightly(ctx: JobContext) -> dict[str, Any]:
    results: dict[str, Any] = {}
    failures: list[str] = []
    total = len(NIGHTLY_STEPS)
    for index, step in enumerate(NIGHTLY_STEPS):
        await ctx.set_progress(int(index * 100 / total), f"{step} ({index + 1}/{total})")
        sub_ctx = JobContext(job_id=ctx.job_id, payload={}, set_progress=ctx.set_progress)
        try:
            results[step] = await get_handler(step)(sub_ctx)
        except Exception as exc:  # un pas caigut no atura la cadena
            failures.append(step)
            results[step] = {"error": f"{type(exc).__name__}: {exc}"}
            logger.warning("nightly_step_failed", step=step, error=str(exc))
    await ctx.set_progress(100, None)
    if failures:
        raise RuntimeError(
            f"Passos fallits: {', '.join(failures)} — resum: {json.dumps(results, default=str)}"
        )

    # Enriquiment automàtic (sync.nightly_enrich, actiu de sèrie), NOMÉS si
    # la cadena ha acabat bé: s'ENCUA com a job independent — mai dins de la
    # cadena, que el job_timeout no mati les sincros si l'enriquiment dura
    # hores. Sense «forçar»: només els expedients no enriquits (els nous).
    results["enrichment_enqueued"] = False
    if await _enrich_enabled():
        results["enrichment_enqueued"] = await _enqueue_enrichment()
    return results


async def _enrich_enabled() -> bool:
    from app.core.db import session_factory

    async with session_factory() as session:
        values = await load_schedule_settings(session)
    return parse_enabled(values.get(SETTING_ENRICH), default=True)


async def _enqueue_enrichment() -> bool:
    from app.core.db import session_factory
    from app.core.problems import Problem
    from app.jobs.service import enqueue_job

    async with session_factory() as session:
        try:
            job_row = await enqueue_job(
                session,
                job_type="enrich.batch",
                payload={"trigger": "scheduled"},
                # Mateixa clau que el llançament manual de la pantalla de
                # sync: mai dos enriquiments alhora, vinguin d'on vinguin.
                dedup_key="trigger:enrich.batch",
            )
        except Problem:
            # Ja n'hi ha un en curs (p. ex. llançat a mà): no es duplica.
            logger.info("nightly_enrichment_already_running")
            return False
        await session.commit()
    logger.info("nightly_enrichment_enqueued", job_id=str(job_row.id))
    return True


_ALL_DAYS = {1, 2, 3, 4, 5, 6, 7}


def parse_enabled(raw: Any, *, default: bool = True) -> bool:
    """No definit = `default`; la nocturna neix activada, l'informe no."""
    if raw is None or raw == "":
        return default
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() not in {"false", "0", "no", "off"}


def parse_interval_days(raw: Any, *, default: int = 30) -> int:
    try:
        days = int(str(raw).strip())
    except (ValueError, TypeError):
        return default
    return days if 1 <= days <= 365 else default


def parse_days(raw: Any) -> set[int]:
    """Dies ISO (1=dl … 7=dg) com a llista JSON o text; invàlid/buit = tots."""
    if raw is None or raw == "":
        return _ALL_DAYS
    value = raw
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return _ALL_DAYS
    if not isinstance(value, list):
        return _ALL_DAYS
    try:
        days = {int(d) for d in value}
    except (ValueError, TypeError):
        return _ALL_DAYS
    days &= _ALL_DAYS
    return days or _ALL_DAYS


def parse_time(raw: Any) -> time:
    try:
        hour, minute = str(raw or _DEFAULT_TIME).strip().split(":")
        return time(int(hour), int(minute))
    except (ValueError, AttributeError):
        return time(2, 30)


def nightly_due(now: datetime, *, enabled_raw: Any, time_raw: Any, days_raw: Any) -> bool:
    """La cadena toca si està activada, és un dia actiu i ja ha passat l'hora.

    El «un cop al dia» el garanteix el caller (clau Redis per data + dedup
    de cua): aquesta funció és pura per poder-la testejar.
    """
    if not parse_enabled(enabled_raw):
        return False
    local = now.astimezone(TIMEZONE)
    if local.isoweekday() not in parse_days(days_raw):
        return False
    return local.time() >= parse_time(time_raw)


async def load_schedule_settings(session: AsyncSession) -> dict[str, Any]:
    from sqlalchemy import select

    from app.modules.config.models import Setting

    rows = (
        await session.execute(
            select(Setting.key, Setting.value).where(
                Setting.key.in_([SETTING_ENABLED, SETTING_TIME, SETTING_DAYS, SETTING_ENRICH])
            )
        )
    ).all()
    return {row.key: row.value for row in rows}
