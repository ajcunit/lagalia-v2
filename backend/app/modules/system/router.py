"""Estat del sistema (specs/system-status.md, B-022): readiness i dashboard.

Lectures agregades de fonts que ja existeixen (jobs, sync_runs,
webhook_deliveries, connector_records) més els pings d'infraestructura
interna. Cap crida a serveis externs: això és feina del job de fons.
"""

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import authz, usage
from app.core.db import get_session
from app.integrations.models import ConnectorRecord
from app.modules.config.models import Setting
from app.modules.system import service as checks
from app.modules.users.models import User

router = APIRouter(tags=["system"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
ReadDep = Annotated[authz.AuthzContext, Depends(authz.Authorize("system:read"))]


class ReadinessResponse(BaseModel):
    status: checks.CheckStatus
    checks: list[checks.ServiceCheck]


class RunningJobInfo(BaseModel):
    id: uuid.UUID
    type: str
    progress: int
    progress_message: str | None
    started_at: datetime | None


class JobsSummary(BaseModel):
    queued: int
    running: int
    dead: int
    failed_24h: int
    running_jobs: list[RunningJobInfo]


class SyncRunSummary(BaseModel):
    kind: str
    status: str
    started_at: datetime | None
    finished_at: datetime | None


class WebhooksSummary(BaseModel):
    pending: int
    failed_24h: int


class ResourcesSummary(BaseModel):
    database_bytes: int | None
    redis_memory_bytes: int | None
    queue_depth: int
    storage_objects: int | None
    storage_bytes: int | None
    storage_truncated: bool | None
    storage_measured_at: datetime | None


class SystemStatusResponse(BaseModel):
    generated_at: datetime
    status: checks.CheckStatus
    services: list[checks.ServiceCheck]
    jobs: JobsSummary
    syncs: list[SyncRunSummary]
    webhooks: WebhooksSummary
    resources: ResourcesSummary


@router.get("/health/ready", operation_id="getReadiness")
async def get_readiness(session: SessionDep, _authz: ReadDep) -> ReadinessResponse:
    """Readiness del contracte de fase 0: només infraestructura, en viu."""
    database = await checks.check_database(session)
    redis_check, _scheduler, _memory = await checks.redis_checks()
    storage = await checks.check_storage()
    infra = [database, redis_check, storage]
    return ReadinessResponse(status=checks.worst_status(infra), checks=infra)


async def _jobs_summary(session: AsyncSession) -> JobsSummary:
    counts = {
        row.status: int(row.total)
        for row in (
            await session.execute(
                text(
                    "SELECT status, count(*) AS total FROM jobs "
                    "WHERE status IN ('queued', 'running', 'dead') GROUP BY status"
                )
            )
        ).all()
    }
    failed_24h = (
        await session.execute(
            text(
                "SELECT count(*) FROM jobs WHERE status IN ('failed', 'dead') "
                "AND finished_at > now() - interval '24 hours'"
            )
        )
    ).scalar_one()
    running_rows = (
        await session.execute(
            text(
                "SELECT id, type, progress, progress_message, started_at FROM jobs "
                "WHERE status = 'running' ORDER BY started_at DESC NULLS LAST LIMIT 20"
            )
        )
    ).all()
    return JobsSummary(
        queued=counts.get("queued", 0),
        running=counts.get("running", 0),
        dead=counts.get("dead", 0),
        failed_24h=int(failed_24h),
        running_jobs=[
            RunningJobInfo(
                id=row.id,
                type=row.type,
                progress=row.progress,
                progress_message=row.progress_message,
                started_at=row.started_at,
            )
            for row in running_rows
        ],
    )


async def _sync_summaries(session: AsyncSession) -> list[SyncRunSummary]:
    rows = (
        await session.execute(
            text(
                "SELECT DISTINCT ON (kind) kind, status, started_at, finished_at "
                "FROM sync_runs ORDER BY kind, started_at DESC NULLS LAST"
            )
        )
    ).all()
    return [
        SyncRunSummary(
            kind=row.kind, status=row.status, started_at=row.started_at, finished_at=row.finished_at
        )
        for row in rows
    ]


async def _webhooks_summary(session: AsyncSession) -> WebhooksSummary:
    pending = (
        await session.execute(
            text("SELECT count(*) FROM webhook_deliveries WHERE status = 'pending'")
        )
    ).scalar_one()
    failed = (
        await session.execute(
            text(
                "SELECT count(*) FROM webhook_deliveries WHERE status = 'failed' "
                "AND updated_at > now() - interval '24 hours'"
            )
        )
    ).scalar_one()
    return WebhooksSummary(pending=int(pending), failed_24h=int(failed))


def _connector_check(record: ConnectorRecord) -> checks.ServiceCheck:
    status: checks.CheckStatus
    if record.health_status == "healthy":
        status = "ok"
    elif record.health_status == "failing":
        status = "failing"
    else:
        # Mai comprovat encara (el job de fons ho farà a la propera passada).
        status = "degraded"
    return checks.ServiceCheck(
        name=f"connector:{record.slug}",
        status=status,
        detail=None if record.health_status == "healthy" else record.health_status,
        checked_at=record.last_health_check,
    )


async def _storage_usage(session: AsyncSession) -> dict[str, Any]:
    setting = (
        await session.execute(select(Setting).where(Setting.key == checks.STORAGE_USAGE_SETTING))
    ).scalar_one_or_none()
    value = setting.value if setting is not None else None
    return value if isinstance(value, dict) else {}


@router.get("/system/status", operation_id="getSystemStatus")
async def get_system_status(session: SessionDep, _authz: ReadDep) -> SystemStatusResponse:
    database = await checks.check_database(session)
    redis_check, scheduler, redis_memory = await checks.redis_checks()
    storage = await checks.check_storage()
    worker = await checks.check_worker(session)

    connectors = [
        _connector_check(record)
        for record in (
            await session.execute(
                select(ConnectorRecord)
                .where(ConnectorRecord.enabled.is_(True))
                .order_by(ConnectorRecord.slug)
            )
        ).scalars()
    ]

    # L'estat global el mana la plataforma (infra + worker + scheduler);
    # un connector extern caigut es veu a la llista però no tomba el global.
    core = [database, redis_check, storage, worker, scheduler]

    usage_snapshot = await _storage_usage(session)
    measured_at_raw = usage_snapshot.get("measured_at")
    measured_at = (
        datetime.fromisoformat(measured_at_raw) if isinstance(measured_at_raw, str) else None
    )
    jobs = await _jobs_summary(session)

    return SystemStatusResponse(
        generated_at=datetime.now(UTC),
        status=checks.worst_status(core),
        services=core + connectors,
        jobs=jobs,
        syncs=await _sync_summaries(session),
        webhooks=await _webhooks_summary(session),
        resources=ResourcesSummary(
            database_bytes=await checks.database_size_bytes(session),
            redis_memory_bytes=redis_memory,
            queue_depth=jobs.queued,
            storage_objects=usage_snapshot.get("objects"),
            storage_bytes=usage_snapshot.get("total_bytes"),
            storage_truncated=usage_snapshot.get("truncated"),
            storage_measured_at=measured_at,
        ),
    )


# ─────────────────── ús de la plataforma (B-010) ───────────────────


class UsageDaySummary(BaseModel):
    day: str
    requests: int
    errors: int


class EndpointUsage(BaseModel):
    endpoint: str
    requests: int
    errors: int


class UserActivity(BaseModel):
    """Qui s'ha connectat i què genera: última connexió de l'audit_log
    (auth.login amb èxit) + peticions del període (comptadors B-010)."""

    user_id: int
    name: str | None
    last_login_at: datetime | None
    last_login_ip: str | None
    requests: int


class ModuleUsage(BaseModel):
    module: str
    label: str
    requests: int


class SystemUsageResponse(BaseModel):
    days: list[UsageDaySummary]
    top_endpoints: list[EndpointUsage]
    top_modules: list[ModuleUsage]
    users: list[UserActivity]
    active_sessions: int
    active_users: int


TOP_LIMIT = 15
USERS_LIMIT = 50


@router.get("/system/usage", operation_id="getSystemUsage")
async def get_system_usage(
    session: SessionDep,
    _authz: ReadDep,
    days: Annotated[int, Query(ge=1, le=40)] = 7,
) -> SystemUsageResponse:
    """Ús de la plataforma (specs/usage-tracking.md): comptadors diaris de
    Redis agregats pel període + sessions actives (refresh tokens vius)."""
    series = await usage.read_usage(days)

    endpoint_totals: dict[str, int] = {}
    endpoint_errors: dict[str, int] = {}
    user_totals: dict[str, int] = {}
    for entry in series:
        for endpoint, count in entry["endpoints"].items():
            endpoint_totals[endpoint] = endpoint_totals.get(endpoint, 0) + count
        for endpoint, count in entry["endpoint_errors"].items():
            endpoint_errors[endpoint] = endpoint_errors.get(endpoint, 0) + count
        for user_id, count in entry["users"].items():
            user_totals[user_id] = user_totals.get(user_id, 0) + count

    top_endpoints = [
        EndpointUsage(endpoint=endpoint, requests=count, errors=endpoint_errors.get(endpoint, 0))
        for endpoint, count in sorted(
            endpoint_totals.items(), key=lambda item: item[1], reverse=True
        )[:TOP_LIMIT]
    ]

    # Mòduls més usats: cada plantilla d'endpoint mapa al seu mòdul amb la
    # mateixa taula que el tall de mòduls desactivats (core/modules.py).
    from app.core.modules import MODULES, module_for_path

    module_totals: dict[str, int] = {}
    for endpoint, count in endpoint_totals.items():
        _method, _, path = endpoint.partition(" ")
        module = module_for_path(f"/api/v1{path}")
        if module is not None:
            module_totals[module] = module_totals.get(module, 0) + count
    top_modules = [
        ModuleUsage(module=module, label=MODULES[module], requests=count)
        for module, count in sorted(module_totals.items(), key=lambda item: item[1], reverse=True)
    ]

    # Qui s'ha connectat: última connexió amb èxit de l'audit_log + les
    # peticions del període. Unió d'ambdues fonts, mai només una.
    logins = (
        await session.execute(
            text(
                "SELECT DISTINCT ON (actor_id) actor_id, occurred_at, host(ip) AS ip "
                "FROM audit_log "
                "WHERE action = 'auth.login' AND success AND actor_id IS NOT NULL "
                "ORDER BY actor_id, occurred_at DESC"
            )
        )
    ).all()
    last_login = {int(row.actor_id): (row.occurred_at, row.ip) for row in logins}

    usage_by_id = {int(raw): count for raw, count in user_totals.items() if raw.isdigit()}
    user_ids = set(last_login) | set(usage_by_id)
    names: dict[int, str] = {}
    if user_ids:
        rows = (
            await session.execute(select(User.id, User.name).where(User.id.in_(user_ids)))
        ).all()
        names = {row.id: row.name for row in rows}
    epoch = datetime.min.replace(tzinfo=UTC)
    users = sorted(
        (
            UserActivity(
                user_id=user_id,
                name=names.get(user_id),
                last_login_at=last_login.get(user_id, (None, None))[0],
                last_login_ip=last_login.get(user_id, (None, None))[1],
                requests=usage_by_id.get(user_id, 0),
            )
            for user_id in user_ids
        ),
        key=lambda u: (u.requests, u.last_login_at or epoch),
        reverse=True,
    )[:USERS_LIMIT]

    active_sessions = (
        await session.execute(
            text(
                "SELECT count(*) FROM refresh_tokens "
                "WHERE revoked_at IS NULL AND expires_at > now()"
            )
        )
    ).scalar_one()
    active_users = (
        await session.execute(
            text(
                "SELECT count(DISTINCT user_id) FROM refresh_tokens "
                "WHERE revoked_at IS NULL AND expires_at > now()"
            )
        )
    ).scalar_one()

    return SystemUsageResponse(
        days=[
            UsageDaySummary(day=e["day"], requests=e["requests"], errors=e["errors"])
            for e in series
        ],
        top_endpoints=top_endpoints,
        top_modules=top_modules,
        users=users,
        active_sessions=int(active_sessions),
        active_users=int(active_users),
    )
