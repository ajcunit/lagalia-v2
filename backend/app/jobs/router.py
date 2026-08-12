"""Endpoints de jobs i token efímer. Prims: la lògica és als serveis."""

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import get_session, session_factory
from app.core.problems import Problem, unauthorized
from app.jobs import ephemeral, events, service
from app.jobs.models import TERMINAL_STATUSES, Job
from app.jobs.schemas import (
    EphemeralTokenRequest,
    EphemeralTokenResponse,
    JobResponse,
)
from app.modules.audit.models import AuditActorType
from app.modules.audit.service import record_audit
from app.modules.users.dependencies import (
    CurrentSession,
    get_current_session,
    get_request_context,
)
from app.modules.users.service import RequestContext

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_session)]
ContextDep = Annotated[RequestContext, Depends(get_request_context)]
CurrentDep = Annotated[CurrentSession, Depends(get_current_session)]

_HEARTBEAT_SECONDS = 15


@router.get("/jobs/{id}", tags=["jobs"], operation_id="getJob")
async def get_job(
    id: uuid.UUID, current: CurrentDep, session: SessionDep, ctx: ContextDep
) -> JobResponse:
    job = await service.get_job_for(session, id, current.user, ctx)
    return JobResponse.from_job(job)


@router.post(
    "/jobs/{id}/actions/cancel",
    tags=["jobs"],
    operation_id="cancelJob",
    status_code=202,
)
async def cancel_job(
    id: uuid.UUID, current: CurrentDep, session: SessionDep, ctx: ContextDep
) -> JobResponse:
    job = await service.cancel_job(session, id, current.user, ctx)
    return JobResponse.from_job(job)


@router.post(
    "/auth/ephemeral",
    tags=["auth"],
    operation_id="createEphemeralToken",
    status_code=201,
)
async def create_ephemeral_token(
    body: EphemeralTokenRequest,
    current: CurrentDep,
    session: SessionDep,
    ctx: ContextDep,
) -> EphemeralTokenResponse:
    try:
        job_id = uuid.UUID(body.resource)
    except ValueError:
        raise Problem(422, "Recurs invàlid", "validation") from None
    # El token només s'emet si l'usuari pot llegir el job.
    await service.get_job_for(session, job_id, current.user, ctx)

    token, expires_at = await ephemeral.issue_token(current.user.id, body.purpose, body.resource)
    await record_audit(
        session,
        actor_type=AuditActorType.USER,
        action="auth.ephemeral",
        success=True,
        actor_id=current.user.id,
        resource_type="job",
        resource_id=body.resource,
        ip=ctx.ip,
        user_agent=ctx.user_agent,
        trace_id=ctx.trace_id,
    )
    await session.commit()
    return EphemeralTokenResponse(token=token, expires_at=expires_at)


async def _current_snapshot(job_id: uuid.UUID) -> dict[str, object] | None:
    async with session_factory() as session:
        job = await session.get(Job, job_id)
        return events.snapshot(job) if job is not None else None


async def _event_stream(job_id: uuid.UUID, initial: dict[str, object]) -> AsyncIterator[str]:
    yield f"event: state\ndata: {json.dumps(initial)}\n\n"
    if initial["status"] in TERMINAL_STATUSES:
        return

    redis = Redis.from_url(settings.redis_url)
    pubsub = redis.pubsub()
    await pubsub.subscribe(events.channel_for(job_id))
    try:
        while True:
            # get_message pot retornar None abans d'esgotar el timeout (p. ex.
            # en consumir la confirmació de subscripció): esgotem el batec.
            deadline = asyncio.get_running_loop().time() + _HEARTBEAT_SECONDS
            message = None
            while message is None:
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    break
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=remaining
                )
            if message is None:
                # Revalida a BD: si el missatge terminal s'ha perdut (publicat
                # abans de subscriure'ns, o Redis reiniciat), tanquem igualment.
                snapshot = await _current_snapshot(job_id)
                if snapshot is not None and snapshot["status"] in TERMINAL_STATUSES:
                    yield f"event: state\ndata: {json.dumps(snapshot)}\n\n"
                    return
                yield ": ping\n\n"  # manté viva la connexió pels proxies
                continue
            payload = json.loads(message["data"])
            yield f"event: state\ndata: {json.dumps(payload)}\n\n"
            if payload.get("status") in TERMINAL_STATUSES:
                return
    finally:
        await pubsub.unsubscribe()
        await pubsub.aclose()
        await redis.aclose()


@router.get("/jobs/{id}/events", tags=["jobs"], operation_id="streamJobEvents")
async def stream_job_events(id: uuid.UUID, token: Annotated[str, Query()]) -> StreamingResponse:
    grant = await ephemeral.consume_token(token)
    if grant is None or grant.purpose != "job_events" or grant.resource != str(id):
        raise unauthorized()

    async with session_factory() as session:
        job = await session.get(Job, id)
        if job is None:
            raise Problem(404, "Treball no trobat", "not-found")
        initial = events.snapshot(job)

    return StreamingResponse(
        _event_stream(id, initial),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
