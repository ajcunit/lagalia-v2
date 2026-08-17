"""Configuració: paràmetres i connectors (specs/config-ui.md). Lectura per a
tothom (config:read, sense secrets); escriptura només admin (config:write)."""

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query
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
from app.modules.config.known_settings import KNOWN_SETTINGS
from app.modules.config.models import Setting
from app.modules.users.dependencies import get_request_context
from app.modules.users.service import RequestContext

router = APIRouter(tags=["config"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
ContextDep = Annotated[RequestContext, Depends(get_request_context)]
ReadDep = Annotated[authz.AuthzContext, Depends(authz.Authorize("config:read"))]
WriteDep = Annotated[authz.AuthzContext, Depends(authz.Authorize("config:write"))]
ExecDep = Annotated[authz.AuthzContext, Depends(authz.Authorize("sync:execute"))]
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
    placeholder: str = ""


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
    """Paràmetres existents + els coneguts encara no creats (editables)."""
    rows = list((await session.execute(select(Setting).order_by(Setting.key))).scalars())
    responses = [_setting_response(row) for row in rows]
    existing = {row.key for row in rows}
    by_key = {item.key: item for item in KNOWN_SETTINGS}
    for response in responses:
        known = by_key.get(response.key)
        if known is not None:
            response.placeholder = known.placeholder
            response.description = response.description or known.description
    for known in KNOWN_SETTINGS:
        if known.key not in existing:
            responses.append(
                SettingResponse(
                    key=known.key,
                    value=None,
                    description=known.description,
                    is_secret=known.is_secret,
                    is_set=False,
                    placeholder=known.placeholder,
                )
            )
    responses.sort(key=lambda item: item.key)
    return {"data": responses}


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
        mode=getattr(record.mode, "value", record.mode),
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


# ─────────────────────── mapejador de camps ───────────────────────
# specs/field-mapping.md: overrides manuals del mapeig font → model.

_MAPPABLE_SOURCES = ("socrata",)
TargetField = Annotated[str, Path(min_length=1, max_length=100, pattern=r"^[a-z0-9_.]+$")]


def _field_defs() -> dict[str, Any]:
    from app.integrations.socrata.mapping import CONTRACTOR_FIELDS, MAPPABLE_FIELDS

    return {**MAPPABLE_FIELDS, **CONTRACTOR_FIELDS}


def _check_mappable_source(slug: str) -> None:
    if slug not in _MAPPABLE_SOURCES:
        raise Problem(404, "Aquesta font no té mapeig de camps", "not-found")


class FieldMappingRow(BaseModel):
    target_field: str
    label: str
    kind: str
    default_source_field: str
    source_field: str
    overridden: bool


class FieldMappingUpdate(BaseModel):
    source_field: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9_]+$")


@router.get("/connectors/{slug}/field-mappings", operation_id="listFieldMappings")
async def list_field_mappings(
    slug: Slug, session: SessionDep, _authz: ReadDep
) -> dict[str, list[FieldMappingRow]]:
    _check_mappable_source(slug)
    from app.integrations.field_mappings import get_overrides

    overrides = await get_overrides(session, slug)
    rows = [
        FieldMappingRow(
            target_field=target,
            label=definition.label,
            kind=definition.kind,
            default_source_field=definition.source,
            source_field=overrides.get(target) or definition.source,
            overridden=target in overrides,
        )
        for target, definition in _field_defs().items()
    ]
    return {"data": rows}


@router.get(
    "/connectors/{slug}/field-mappings/sample", operation_id="getFieldMappingSample"
)
async def get_field_mapping_sample(
    slug: Slug,
    file_code: Annotated[str, Query(min_length=1, max_length=100)],
    session: SessionDep,
    _authz: ReadDep,
) -> dict[str, Any]:
    """La fila `raw` guardada d'un expedient sincronitzat (cap crida externa)."""
    _check_mappable_source(slug)
    from sqlalchemy import text as sql_text

    row = (
        await session.execute(
            sql_text(
                "SELECT raw FROM contracts WHERE file_code = :f AND raw IS NOT NULL "
                "ORDER BY id DESC LIMIT 1"
            ),
            {"f": file_code},
        )
    ).first()
    if row is None:
        raise Problem(
            404,
            "Expedient sense fila sincronitzada: només es poden mostrar camps "
            "d'expedients que ja són a la base de dades",
            "not-found",
        )
    return {"file_code": file_code, "fields": row.raw}


@router.put(
    "/connectors/{slug}/field-mappings/{target_field}", operation_id="setFieldMapping"
)
async def set_field_mapping(
    slug: Slug,
    target_field: TargetField,
    body: FieldMappingUpdate,
    session: SessionDep,
    authz_ctx: WriteDep,
    ctx: ContextDep,
) -> FieldMappingRow:
    _check_mappable_source(slug)
    definition = _field_defs().get(target_field)
    if definition is None:
        raise Problem(404, "Camp de destí desconegut", "not-found")
    from sqlalchemy import text as sql_text

    await session.execute(
        sql_text(
            "INSERT INTO field_mappings (source, target_field, source_field, updated_by) "
            "VALUES (:s, :t, :f, :u) "
            "ON CONFLICT ON CONSTRAINT uq_field_mappings_source_target "
            "DO UPDATE SET source_field = :f, updated_by = :u, updated_at = now()"
        ),
        {"s": slug, "t": target_field, "f": body.source_field, "u": authz_ctx.user.id},
    )
    await _audit(
        session,
        authz_ctx.user.id,
        "config.field_mapping_updated",
        f"{slug}:{target_field}={body.source_field}",
        ctx,
    )
    await session.commit()
    return FieldMappingRow(
        target_field=target_field,
        label=definition.label,
        kind=definition.kind,
        default_source_field=definition.source,
        source_field=body.source_field,
        overridden=body.source_field != definition.source,
    )


@router.delete(
    "/connectors/{slug}/field-mappings/{target_field}",
    operation_id="resetFieldMapping",
    status_code=204,
)
async def reset_field_mapping(
    slug: Slug,
    target_field: TargetField,
    session: SessionDep,
    authz_ctx: WriteDep,
    ctx: ContextDep,
) -> None:
    _check_mappable_source(slug)
    from sqlalchemy import text as sql_text

    await session.execute(
        sql_text(
            "DELETE FROM field_mappings WHERE source = :s AND target_field = :t"
        ),
        {"s": slug, "t": target_field},
    )
    await _audit(
        session, authz_ctx.user.id, "config.field_mapping_reset", f"{slug}:{target_field}", ctx
    )
    await session.commit()


@router.post(
    "/connectors/{slug}/actions/remap", operation_id="remapContracts", status_code=202
)
async def remap_contracts_action(
    slug: Slug, session: SessionDep, authz_ctx: ExecDep, ctx: ContextDep
) -> dict[str, Any]:
    """Re-aplica el mapeig vigent sobre el raw guardat (job local, cap crida externa)."""
    _check_mappable_source(slug)
    from app.jobs.service import enqueue_job

    job = await enqueue_job(
        session,
        job_type="sync.remap_contracts",
        payload={},
        created_by=authz_ctx.user.id or None,
        dedup_key="trigger:sync.remap_contracts",
    )
    await _audit(session, authz_ctx.user.id, "config.remap_triggered", slug, ctx)
    await session.commit()
    return {"job_id": str(job.id), "job_type": "sync.remap_contracts"}
