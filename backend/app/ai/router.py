"""Gestió de perfils de proveïdor d'IA i execucions (specs/ai-providers.md)."""

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import analyst_agent, audit_agent, cpv_agent, providers
from app.ai import tasks as ai_tasks
from app.ai.models import AiProtocol, AiProviderProfile, AiRun, AiTaskConfig
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


UseDep = Annotated[authz.AuthzContext, Depends(authz.Authorize("tools:use"))]


class CpvSuggestBody(BaseModel):
    text: str = Field(min_length=5, max_length=2000)


class CpvFeedbackBody(BaseModel):
    query_text: str = Field(min_length=1, max_length=2000)
    chosen_code: str = Field(min_length=8, max_length=20)
    suggested: list[dict[str, Any]] | None = None


@router.post("/ai/cpv/suggest", operation_id="suggestCpv")
async def suggest_cpv(
    body: CpvSuggestBody, session: SessionDep, authz_ctx: UseDep, ctx: ContextDep
) -> dict[str, Any]:
    """Agent classificador CPV (specs/cpv-ai-suggest.md); resol proveïdor per tasca."""
    return await cpv_agent.suggest(
        session, body.text, user_id=authz_ctx.user.id, trace_id=ctx.trace_id
    )


AuditRunDep = Annotated[authz.AuthzContext, Depends(authz.Authorize("audit:run"))]


class AuditReportBody(BaseModel):
    custom_prompt: str | None = Field(default=None, max_length=2000)


@router.post("/ai/audit/report", operation_id="generateAuditReport")
async def generate_audit_report(
    body: AuditReportBody, session: SessionDep, authz_ctx: AuditRunDep, ctx: ContextDep
) -> dict[str, Any]:
    """Agent auditor (specs/audit-ai-report.md): informe executiu en Markdown."""
    try:
        return await audit_agent.generate_report(
            session,
            custom_prompt=body.custom_prompt,
            user_id=authz_ctx.user.id,
            trace_id=ctx.trace_id,
        )
    except providers.ProviderError as exc:
        raise Problem(502, "El proveïdor d'IA no ha respost", "upstream", detail=str(exc)) from None


class AnalysisBody(BaseModel):
    question: str = Field(min_length=5, max_length=2000)


@router.post("/ai/analyses", operation_id="createAnalysis")
async def create_analysis(
    body: AnalysisBody, session: SessionDep, authz_ctx: AuditRunDep, ctx: ContextDep
) -> dict[str, Any]:
    """Agent analista (specs/ai-analyst.md): pregunta → resposta amb dades font."""
    try:
        return await analyst_agent.answer_question(
            session, body.question, user_id=authz_ctx.user.id, trace_id=ctx.trace_id
        )
    except providers.ProviderError as exc:
        raise Problem(502, "El proveïdor d'IA no ha respost", "upstream", detail=str(exc)) from None


class TaskConfigBody(BaseModel):
    provider_profile_id: int
    model: str | None = Field(default=None, max_length=200)
    max_tokens: int | None = Field(default=None, ge=1, le=200000)


@router.get("/ai/tasks", operation_id="listAiTasks")
async def list_ai_tasks(session: SessionDep, _authz: WriteDep) -> dict[str, list[dict[str, Any]]]:
    configs = {
        c.task: c
        for c in (await session.execute(select(AiTaskConfig))).scalars()
    }
    data = []
    for task, description in ai_tasks.KNOWN_TASKS.items():
        config = configs.get(task)
        try:
            resolved = await ai_tasks.resolve(session, task)
            effective = {
                "profile_id": resolved.profile.id,
                "profile_name": resolved.profile.name,
                "model": resolved.model or resolved.profile.default_model,
            }
        except Problem:
            effective = None
        data.append(
            {
                "task": task,
                "description": description,
                "config": {
                    "provider_profile_id": config.provider_profile_id,
                    "model": config.model,
                    "max_tokens": config.max_tokens,
                }
                if config
                else None,
                "effective": effective,
            }
        )
    return {"data": data}


@router.put("/ai/tasks/{task}", operation_id="setAiTaskConfig")
async def set_ai_task_config(
    task: str, body: TaskConfigBody, session: SessionDep, authz_ctx: WriteDep, ctx: ContextDep
) -> dict[str, str]:
    if task not in ai_tasks.KNOWN_TASKS:
        raise Problem(404, "Tasca desconeguda", "not-found")
    if await session.get(AiProviderProfile, body.provider_profile_id) is None:
        raise Problem(404, "Perfil desconegut", "not-found")
    config = (
        await session.execute(select(AiTaskConfig).where(AiTaskConfig.task == task))
    ).scalar_one_or_none()
    if config is None:
        config = AiTaskConfig(task=task, provider_profile_id=body.provider_profile_id)
        session.add(config)
    config.provider_profile_id = body.provider_profile_id
    config.model = body.model
    config.max_tokens = body.max_tokens
    await _audit(session, authz_ctx.user.id, "ai.task_configured", task, ctx)
    await session.commit()
    return {"status": "saved"}


@router.delete("/ai/tasks/{task}", operation_id="resetAiTaskConfig", status_code=204)
async def reset_ai_task_config(
    task: str, session: SessionDep, authz_ctx: WriteDep, ctx: ContextDep
) -> None:
    config = (
        await session.execute(select(AiTaskConfig).where(AiTaskConfig.task == task))
    ).scalar_one_or_none()
    if config is not None:
        await session.delete(config)
        await _audit(session, authz_ctx.user.id, "ai.task_reset", task, ctx)
        await session.commit()


@router.post("/ai/cpv/feedback", operation_id="recordCpvFeedback", status_code=201)
async def record_cpv_feedback(
    body: CpvFeedbackBody, session: SessionDep, authz_ctx: UseDep, ctx: ContextDep
) -> dict[str, str]:
    from sqlalchemy import text as sql_text

    await session.execute(
        sql_text(
            "INSERT INTO ai_cpv_feedback (query_text, chosen_code, suggested, user_id) "
            "VALUES (:q, :c, CAST(:s AS jsonb), :u)"
        ),
        {
            "q": body.query_text,
            "c": body.chosen_code,
            "s": __import__("json").dumps(body.suggested) if body.suggested else None,
            "u": authz_ctx.user.id,
        },
    )
    await session.commit()
    return {"status": "recorded"}


class TestPromptBody(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)
    model: str | None = Field(default=None, max_length=200)


@router.post("/ai/providers/{id}/actions/test-completion", operation_id="testAiProvider")
async def test_completion(
    id: int, body: TestPromptBody, session: SessionDep, authz_ctx: WriteDep, ctx: ContextDep
) -> dict[str, Any]:
    """Provador d'admin (síncron, com el healthcheck): compleció curta i
    registrada a ai_runs; mai tomba l'API."""
    profile = await _get_profile(session, id)
    try:
        result = await providers.complete(
            profile,
            [
                {
                    "role": "system",
                    "content": "Ets l'assistent de la plataforma de contractació LAGALia. "
                    "Respon en català i de manera breu.",
                },
                {"role": "user", "content": body.prompt},
            ],
            task="admin.test_completion",
            model=body.model,
            max_tokens=20000,
            user_id=authz_ctx.user.id,
            trace_id=ctx.trace_id,
            input_summary="provador d'admin",
        )
    except providers.ProviderError as exc:
        return {"status": "error", "detail": str(exc)}
    except Exception as exc:  # defensa: mai tomba l'API
        return {"status": "error", "detail": f"{type(exc).__name__}: {exc}"}
    return {
        "status": "ok",
        "content": result.content[:8000],
        "model": result.model,
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
    }


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
