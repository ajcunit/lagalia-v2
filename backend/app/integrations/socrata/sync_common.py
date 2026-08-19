"""Peces compartides dels jobs de sync Socrata."""

import unicodedata
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select

from app.core.db import session_factory
from app.integrations.models import SyncItemLog, SyncKind, SyncRun, SyncStatus, SyncTrigger
from app.modules.config.models import Setting


def normalize_text(value: str) -> str:
    """Sense accents i en minúscules, per a discriminadors robustos."""
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


def classify_situacio(value: Any) -> str:
    """Discriminador d'A1 §9 sobre situaci_contractual (verificat al dataset)."""
    normalized = normalize_text(str(value or ""))
    if "prorroga" in normalized:
        return "extension"
    if "modificaci" in normalized:
        return "modification"
    if "liquidaci" in normalized:
        return "settlement"
    if normalized == "menor":
        return "minor_award"
    return "other"


def parse_amount(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def parse_int(value: Any) -> int | None:
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return None


def parse_date_value(value: Any) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)).date()
    except ValueError:
        return None


async def required_ine10() -> str:
    async with session_factory() as session:
        setting = (
            await session.execute(select(Setting).where(Setting.key == "org.ine10_code"))
        ).scalar_one_or_none()
    if setting is None or not setting.value:
        raise RuntimeError("org.ine10_code no configurat (setup)")
    return str(setting.value)


async def create_run(
    kind: SyncKind, trigger: SyncTrigger, *, job_id: uuid.UUID | None = None
) -> int:
    """`job_id` lliga l'execució al treball que la fa: sense el vincle,
    una execució tallada a mig fer es queda «executant» per sempre (B-021)."""
    async with session_factory() as session:
        run = SyncRun(kind=kind, trigger=trigger, started_at=datetime.now(UTC), job_id=job_id)
        session.add(run)
        await session.commit()
        return run.id


async def finish_run(
    run_id: int,
    *,
    status: SyncStatus,
    counters: dict[str, int],
    total_source: int,
    endpoint: str | None,
    error_summary: dict[str, Any] | None = None,
) -> None:
    async with session_factory() as session:
        run = await session.get(SyncRun, run_id)
        if run is None:
            return
        run.status = status
        run.finished_at = datetime.now(UTC)
        run.new_count = counters.get("new", 0)
        run.updated_count = counters.get("updated", 0)
        run.unchanged_count = counters.get("unchanged", 0)
        run.total_source = total_source
        run.endpoint = endpoint
        run.error_summary = error_summary

        from app.modules.webhooks.service import emit_event

        await emit_event(
            session,
            event_type="sync.completed",
            aggregate="sync_run",
            aggregate_id=run_id,
            data={"kind": run.kind.value, "status": status.value, **counters},
        )
        await session.commit()
        from app.modules.webhooks.service import enqueue_dispatch

        await enqueue_dispatch(session)


async def fail_run(run_id: int, exc: Exception) -> None:
    async with session_factory() as session:
        run = await session.get(SyncRun, run_id)
        if run is not None:
            run.status = SyncStatus.FAILED
            run.finished_at = datetime.now(UTC)
            run.error_summary = {"error": f"{type(exc).__name__}: {exc}"}

            from app.modules.webhooks.service import emit_event

            await emit_event(
                session,
                event_type="sync.failed",
                aggregate="sync_run",
                aggregate_id=run_id,
                data={"kind": run.kind.value, "error": f"{type(exc).__name__}: {exc}"},
            )
            await session.commit()
            from app.modules.webhooks.service import enqueue_dispatch

            await enqueue_dispatch(session)


async def log_item(run_id: int, file_code: str, outcome: str, message: str) -> None:
    async with session_factory() as session:
        session.add(
            SyncItemLog(
                sync_run_id=run_id,
                file_code=file_code[:100],
                outcome=outcome,
                message=message[:1000],
            )
        )
        await session.commit()
