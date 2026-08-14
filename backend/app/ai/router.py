"""Gestió de perfils de proveïdor d'IA i execucions (specs/ai-providers.md)."""

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import providers
from app.ai.models import AiProtocol, AiProviderProfile, AiRun
from app.core import authz, crypto
from app.core.db import get_session
from app.core.pagination import PageMeta, decode_cursor, encode_cursor, keyset_condition
from app.core.problems import Problem
from app.modules.audit.models import AuditActorType
from app.modules.audit.service import record_audit
from app.modules.users.dependencies import get_request_context
from app.modules.users.service import RequestContext

router = APIRouter(tags=["ai"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
ContextDep = Annotated[RequestContext, Depends(get_request_context)]
WriteDep = Annotated[authz.AuthzContext, Depends(authz.Authorize("config:write"))]


class ProfileBody(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    protocol: AiProtocol
    base_url: HttpUrl
    default_model: str | None = Field(default=None, max_length=200)


class ProfilePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    base_url: HttpUrl | None = None
    default_model: str | None = Field(default=None, max_length=200)
    enabled: bool | None = None


class ApiKeyBody(BaseModel):
    api_key: str = Field(min_length=1, max_length=500)


class ProfileResponse(BaseModel):
    id: int
    name: str
    protocol: AiProtocol
    base_url: str
    default_model: str | None
    api_key_set: bool
    enabled: bool
    health_status: str | None
    last_health_check: datetime | None


def _profile_response(p: AiProviderProfile) -> ProfileResponse:
    return ProfileResponse(
        id=p.id,
        name=p.name,
        protocol=p.protocol,
        base_url=p.base_url,
        default_model=p.default_model,
        api_key_set=p.api_key_encrypted is not None,
        enabled=p.enabled,
        health_status=p.health_status,
        last_health_check=p.last_health_check,
    )


async def _get_profile(session: AsyncSession, id: int) -> AiProviderProfile:
    profile = await session.get(AiProviderProfile, id)
    if profile is None:
        raise Problem(404, "Perfil desconegut", "not-found")
    return profile


async def _audit(
    session: AsyncSession, user_id: int, action: str, resource: str, ctx: RequestContext
) -> None:
    await record_audit(
        session, actor_type=AuditActorType.USER, action=action, success=True,
        actor_id=user_id, resource_type="ai_provider", resource_id=resource,
        ip=ctx.ip, user_agent=ctx.user_agent, trace_id=ctx.trace_id,
    )


@router.get("/ai/providers", operation_id="listAiProviders")
async def list_providers(
    session: SessionDep, _authz: WriteDep
) -> dict[str, list[ProfileResponse]]:
    rows = (
        await session.execute(select(AiProviderProfile).order_by(AiProviderProfile.name))
    ).scalars()
    return {"data": [_profile_response(p) for p in rows]}


@router.post("/ai/providers", operation_id="createAiProvider", status_code=201)
async def create_provider(
    body: ProfileBody, session: SessionDep, authz_ctx: WriteDep, ctx: ContextDep
) -> ProfileResponse:
    profile = AiProviderProfile(
        name=body.name,
        protocol=body.protocol,
        base_url=str(body.base_url).rstrip("/"),
        default_model=body.default_model,
    )
    session.add(profile)
    await session.flush()
    await _audit(session, authz_ctx.user.id, "ai.provider_created", str(profile.id), ctx)
    await session.commit()
    return _profile_response(profile)


@router.patch("/ai/providers/{id}", operation_id="updateAiProvider")
async def update_provider(
    id: int, body: ProfilePatch, session: SessionDep, authz_ctx: WriteDep, ctx: ContextDep
) -> ProfileResponse:
    profile = await _get_profile(session, id)
    if body.name is not None:
        profile.name = body.name
    if body.base_url is not None:
        profile.base_url = str(body.base_url).rstrip("/")
    if body.default_model is not None:
        profile.default_model = body.default_model
    if body.enabled is not None:
        profile.enabled = body.enabled
    await _audit(session, authz_ctx.user.id, "ai.provider_updated", str(id), ctx)
    await session.commit()
    return _profile_response(profile)


@router.put("/ai/providers/{id}/api-key", operation_id="setAiProviderApiKey")
async def set_api_key(
    id: int, body: ApiKeyBody, session: SessionDep, authz_ctx: WriteDep, ctx: ContextDep
) -> ProfileResponse:
    profile = await _get_profile(session, id)
    profile.api_key_encrypted = crypto.encrypt_value(body.api_key)
    await _audit(session, authz_ctx.user.id, "ai.provider_key_set", str(id), ctx)
    await session.commit()
    return _profile_response(profile)


@router.delete("/ai/providers/{id}", operation_id="deleteAiProvider", status_code=204)
async def delete_provider(
    id: int, session: SessionDep, authz_ctx: WriteDep, ctx: ContextDep
) -> None:
    profile = await _get_profile(session, id)
    await session.delete(profile)
    await _audit(session, authz_ctx.user.id, "ai.provider_deleted", str(id), ctx)
    await session.commit()


@router.post("/ai/providers/{id}/actions/healthcheck", operation_id="checkAiProviderHealth")
async def check_provider_health(
    id: int, session: SessionDep, _authz: WriteDep
) -> dict[str, Any]:
    """Prova de connexió + autodetecció de models; mai tomba l'API."""
    profile = await _get_profile(session, id)
    models: list[str] = []
    try:
        models = await providers.list_models(profile)
        status, detail = "healthy", None
    except providers.ProviderError as exc:
        status, detail = "failing", str(exc)
    except Exception as exc:  # defensa: mai tomba l'API
        status, detail = "failing", f"{type(exc).__name__}: {exc}"
    profile.health_status = status
    profile.last_health_check = datetime.now(UTC)
    await session.commit()
    return {"status": status, "detail": detail, "models": models[:100]}


@router.get("/ai/runs", operation_id="listAiRuns")
async def list_runs(
    session: SessionDep,
    _authz: WriteDep,
    page_size: Annotated[int, Query(alias="page[size]", ge=1, le=100)] = 25,
    page_cursor: Annotated[str | None, Query(alias="page[cursor]")] = None,
    task: Annotated[str | None, Query(alias="filter[task]", max_length=100)] = None,
    status: Annotated[str | None, Query(alias="filter[status]", max_length=20)] = None,
) -> dict[str, Any]:
    conditions = []
    if task:
        conditions.append(AiRun.task == task)
    if status:
        conditions.append(AiRun.status == status)
    total = (
        await session.execute(select(func.count()).select_from(AiRun).where(*conditions))
    ).scalar_one()
    query = select(AiRun).where(*conditions).order_by(AiRun.id.desc()).limit(page_size + 1)
    if page_cursor:
        _, last_id = decode_cursor(page_cursor)
        query = query.where(keyset_condition(AiRun.id, AiRun.id, last_id, last_id, descending=True))
    rows = list((await session.execute(query)).scalars())
    has_more = len(rows) > page_size
    rows = rows[:page_size]
    next_cursor = encode_cursor([rows[-1].id, rows[-1].id]) if has_more and rows else None
    return {
        "data": [
            {
                "id": r.id,
                "task": r.task,
                "agent": r.agent,
                "provider_profile_id": r.provider_profile_id,
                "model": r.model,
                "input_tokens": r.input_tokens,
                "output_tokens": r.output_tokens,
                "latency_ms": r.latency_ms,
                "status": r.status,
                "error_detail": r.error_detail,
                "created_at": r.created_at,
            }
            for r in rows
        ],
        "meta": PageMeta(total=total, next_cursor=next_cursor).model_dump(),
    }
