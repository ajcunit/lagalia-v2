"""Configuració: paràmetres i connectors (specs/config-ui.md). Lectura per a
tothom (config:read, sense secrets); escriptura només admin (config:write)."""

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import authz
from app.core.db import get_session
from app.core.problems import Problem
from app.integrations import hub
from app.integrations.models import ConnectorCredential
from app.modules.audit.models import AuditActorType
from app.modules.audit.service import record_audit
from app.modules.config.models import Setting
from app.modules.users.dependencies import get_request_context
from app.modules.users.service import RequestContext

router = APIRouter(tags=["config"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
ContextDep = Annotated[RequestContext, Depends(get_request_context)]
ReadDep = Annotated[authz.AuthzContext, Depends(authz.Authorize("config:read"))]
WriteDep = Annotated[authz.AuthzContext, Depends(authz.Authorize("config:write"))]
Slug = Annotated[str, Path(min_length=2, max_length=50, pattern="^[a-z0-9_-]+$")]


async def _audit(
    session: AsyncSession, user_id: int, action: str, resource: str, ctx: RequestContext
) -> None:
    await record_audit(
        session,
        actor_type=AuditActorType.USER,
        action=action,
        success=True,
        actor_id=user_id,
        resource_type="config",
        resource_id=resource,
        ip=ctx.ip,
        user_agent=ctx.user_agent,
        trace_id=ctx.trace_id,
    )


# ─────────────────────────── paràmetres ───────────────────────────


class SettingResponse(BaseModel):
    key: str
    value: Any = None
    description: str | None = None
    is_secret: bool
    is_set: bool


class SettingUpdate(BaseModel):
    value: Any = None
    description: str | None = Field(default=None, max_length=500)
    is_secret: bool = False


def _setting_response(setting: Setting) -> SettingResponse:
    return SettingResponse(
        key=setting.key,
        # Els secrets mai es retornen: només is_set (06 §2).
        value=None if setting.is_secret else setting.value,
        description=setting.description,
        is_secret=setting.is_secret,
        is_set=setting.value is not None,
    )


@router.get("/settings", operation_id="listSettings")
async def list_settings(session: SessionDep, _authz: ReadDep) -> dict[str, list[SettingResponse]]:
    settings_rows = (await session.execute(select(Setting).order_by(Setting.key))).scalars()
    return {"data": [_setting_response(s) for s in settings_rows]}


@router.put("/settings/{key}", operation_id="putSetting")
async def put_setting(
    key: Annotated[str, Path(min_length=2, max_length=100)],
    body: SettingUpdate,
    session: SessionDep,
    authz_ctx: WriteDep,
    ctx: ContextDep,
) -> SettingResponse:
    setting = (
        await session.execute(select(Setting).where(Setting.key == key))
    ).scalar_one_or_none()
    if setting is None:
        setting = Setting(key=key, is_secret=body.is_secret)
        session.add(setting)
    setting.value = body.value
    if body.description is not None:
        setting.description = body.description
    setting.is_secret = body.is_secret or setting.is_secret
    setting.updated_by = authz_ctx.user.id
    await session.flush()
    await _audit(session, authz_ctx.user.id, "config.setting_updated", key, ctx)
    await session.commit()
    return _setting_response(setting)


# ─────────────────────────── connectors ───────────────────────────


class ConnectorResponse(BaseModel):
    slug: str
    name: str
    enabled: bool
    mode: str
    config: dict[str, Any]
    config_defaults: dict[str, Any]
    credentials: dict[str, bool]  # nom → is_set (mai el valor)
    health_status: str | None = None
    last_health_check: datetime | None = None


class ConnectorUpdate(BaseModel):
    enabled: bool | None = None
    config: dict[str, Any] | None = None


class CredentialsUpdate(BaseModel):
    credentials: dict[str, str] = Field(min_length=1, max_length=10)


async def _connector_response(session: AsyncSession, slug: str) -> ConnectorResponse:
    manifest, _ = hub._require_known(slug)
    record = await hub.ensure_registered(session, slug)
    set_names = set(
        (
            await session.execute(
                select(ConnectorCredential.name).where(
                    ConnectorCredential.connector_id == record.id
                )
            )
        ).scalars()
    )
    return ConnectorResponse(
        slug=slug,
        name=manifest.name,
        enabled=record.enabled,
        mode=record.mode.value,
        config={**manifest.config_defaults, **(record.config or {})},
        config_defaults=manifest.config_defaults,
        credentials={name: name in set_names for name in manifest.credentials},
        health_status=record.health_status,
        last_health_check=record.last_health_check,
    )


@router.get("/connectors", operation_id="listConnectors")
async def list_connectors(
    session: SessionDep, _authz: ReadDep
) -> dict[str, list[ConnectorResponse]]:
    data = [await _connector_response(session, slug) for slug in sorted(hub.known_slugs())]
    await session.commit()  # ensure_registered pot haver creat files
    return {"data": data}


@router.patch("/connectors/{slug}", operation_id="updateConnector")
async def update_connector(
    slug: Slug, body: ConnectorUpdate, session: SessionDep, authz_ctx: WriteDep, ctx: ContextDep
) -> ConnectorResponse:
    if slug not in hub.known_slugs():
        raise Problem(404, "Connector desconegut", "not-found")
    record = await hub.ensure_registered(session, slug)
    if body.enabled is not None:
        record.enabled = body.enabled
    if body.config is not None:
        manifest, _ = hub._require_known(slug)
        unknown = sorted(set(body.config) - set(manifest.config_defaults))
        if unknown:
            raise Problem(
                422, "Claus de config desconegudes", "validation", detail=", ".join(unknown)
            )
        record.config = {**(record.config or {}), **body.config}
    await session.flush()
    await _audit(session, authz_ctx.user.id, "config.connector_updated", slug, ctx)
    await session.commit()
    response = await _connector_response(session, slug)
    await session.commit()
    return response


@router.put("/connectors/{slug}/credentials", operation_id="putConnectorCredentials")
async def put_connector_credentials(
    slug: Slug,
    body: CredentialsUpdate,
    session: SessionDep,
    authz_ctx: WriteDep,
    ctx: ContextDep,
) -> ConnectorResponse:
    if slug not in hub.known_slugs():
        raise Problem(404, "Connector desconegut", "not-found")
    manifest, _ = hub._require_known(slug)
    unknown = sorted(set(body.credentials) - set(manifest.credentials))
    if unknown:
        raise Problem(422, "Credencials desconegudes", "validation", detail=", ".join(unknown))
    record = await hub.ensure_registered(session, slug)
    for name, value in body.credentials.items():
        await hub.set_credential(session, record.id, name, value)
    await _audit(session, authz_ctx.user.id, "config.connector_credentials", slug, ctx)
    await session.commit()
    response = await _connector_response(session, slug)
    await session.commit()
    return response


@router.post("/connectors/{slug}/actions/healthcheck", operation_id="checkConnectorHealth")
async def check_connector_health(
    slug: Slug, session: SessionDep, _authz: WriteDep
) -> dict[str, Any]:
    if slug not in hub.known_slugs():
        raise Problem(404, "Connector desconegut", "not-found")
    record = await hub.ensure_registered(session, slug)
    try:
        connector = await hub.get_connector(session, slug)
        health = await connector.healthcheck()
        status, detail = ("healthy" if health.healthy else "failing"), health.detail
    except Problem:
        status, detail = "disabled", "el connector està desactivat"
    except Exception as exc:  # healthcheck mai ha de tombar l'API
        status, detail = "failing", f"{type(exc).__name__}: {exc}"
    record.health_status = status
    record.last_health_check = datetime.now(UTC)
    await session.commit()
    return {"status": status, "detail": detail}


@router.post("/connectors/smtp/actions/send-test-email", operation_id="sendSmtpTestEmail")
async def send_smtp_test_email(
    session: SessionDep, authz_ctx: WriteDep, ctx: ContextDep
) -> dict[str, Any]:
    """Envia un correu de prova a l'admin autenticat. Diagnòstic explícit
    d'admin, com el healthcheck: síncron i mai tomba l'API."""
    to = authz_ctx.user.email
    try:
        connector = await hub.get_connector(session, "smtp")
        await connector.send_mail(
            [to],
            "Prova de correu de LAGALia",
            "Això és un correu de prova enviat des de la pantalla de configuració "
            "de LAGALia. Si el llegeixes, el connector SMTP funciona.",
        )
        status, detail = "sent", f"correu enviat a {to}"
    except Problem:
        status, detail = "failed", "el connector smtp està desactivat"
    except Exception as exc:  # mai ha de tombar l'API
        status, detail = "failed", f"{type(exc).__name__}: {exc}"
    await _audit(session, authz_ctx.user.id, "config.smtp_test_email", status, ctx)
    await session.commit()
    return {"status": status, "detail": detail}
