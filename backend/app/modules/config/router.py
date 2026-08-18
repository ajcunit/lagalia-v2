"""Configuració: paràmetres i connectors (specs/config-ui.md). Lectura per a
tothom (config:read, sense secrets); escriptura només admin (config:write)."""

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
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
from app.modules.departments.models import Department
from app.modules.users.dependencies import get_request_context
from app.modules.users.models import LdapGroupMapping, UserRole
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


# ─────────────────────── mapatges LDAP (specs/ldap-auth.md) ───────────────────────


class LdapMappingCreate(BaseModel):
    ad_group: str = Field(min_length=2, max_length=500)
    # Exactament un dels dos: regla de rol (dona accés) o de departament.
    role: UserRole | None = None
    department_id: int | None = None


class LdapMappingResponse(BaseModel):
    id: int
    ad_group: str
    role: UserRole | None
    department_id: int | None
    department_name: str | None


async def _ldap_mapping_rows(session: AsyncSession) -> list[LdapMappingResponse]:
    rows = (
        await session.execute(
            select(LdapGroupMapping, Department.name)
            .join(Department, Department.id == LdapGroupMapping.department_id, isouter=True)
            .order_by(LdapGroupMapping.role.isnot(None).desc(), LdapGroupMapping.ad_group)
        )
    ).all()
    return [
        LdapMappingResponse(
            id=mapping.id,
            ad_group=mapping.ad_group,
            role=mapping.role,
            department_id=mapping.department_id,
            department_name=department_name,
        )
        for mapping, department_name in rows
    ]


@router.get("/ldap/group-mappings", operation_id="listLdapGroupMappings")
async def list_ldap_group_mappings(
    session: SessionDep, _authz: ReadDep
) -> dict[str, list[LdapMappingResponse]]:
    return {"data": await _ldap_mapping_rows(session)}


@router.post("/ldap/group-mappings", operation_id="createLdapGroupMapping", status_code=201)
async def create_ldap_group_mapping(
    body: LdapMappingCreate, session: SessionDep, authz_ctx: WriteDep, ctx: ContextDep
) -> LdapMappingResponse:
    if (body.role is None) == (body.department_id is None):
        raise Problem(
            422,
            "Cada regla és de rol O de departament: exactament un dels dos camps",
            "validation",
        )
    ad_group = body.ad_group.strip()
    duplicate = (
        await session.execute(
            select(LdapGroupMapping.id).where(
                func.lower(LdapGroupMapping.ad_group) == ad_group.lower()
            )
        )
    ).scalar_one_or_none()
    if duplicate is not None:
        raise Problem(409, "Ja hi ha una regla per a aquest grup", "conflict")
    if body.department_id is not None:
        department = await session.get(Department, body.department_id)
        if department is None:
            raise Problem(404, "Departament desconegut", "not-found")
    mapping = LdapGroupMapping(
        ad_group=ad_group, role=body.role, department_id=body.department_id
    )
    session.add(mapping)
    await session.flush()
    await _audit(session, authz_ctx.user.id, "config.ldap_mapping_created", ad_group, ctx)
    await session.commit()
    rows = await _ldap_mapping_rows(session)
    return next(row for row in rows if row.id == mapping.id)


@router.delete(
    "/ldap/group-mappings/{mapping_id}",
    operation_id="deleteLdapGroupMapping",
    status_code=204,
)
async def delete_ldap_group_mapping(
    mapping_id: int, session: SessionDep, authz_ctx: WriteDep, ctx: ContextDep
) -> None:
    mapping = await session.get(LdapGroupMapping, mapping_id)
    if mapping is None:
        raise Problem(404, "Regla desconeguda", "not-found")
    await session.delete(mapping)
    await _audit(session, authz_ctx.user.id, "config.ldap_mapping_deleted", mapping.ad_group, ctx)
    await session.commit()


class LdapTestStep(BaseModel):
    step: str
    ok: bool
    detail: str | None = None


class LdapTestLoginBody(BaseModel):
    username: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=255)


class LdapTestLoginResponse(BaseModel):
    ok: bool
    steps: list[LdapTestStep]
    groups: list[str]
    matched_role: UserRole | None
    matched_department_names: list[str]
    email: str | None
    name: str | None


@router.post("/connectors/ldap/actions/test-login", operation_id="testLdapLogin")
async def test_ldap_login(
    body: LdapTestLoginBody, session: SessionDep, authz_ctx: WriteDep, ctx: ContextDep
) -> LdapTestLoginResponse:
    """Prova un inici de sessió contra l'AD pas a pas, sense tocar cap
    usuari: diagnòstic d'admin per configurar la connexió i les regles.
    La contrasenya no es desa ni s'audita mai."""
    from app.integrations.base import ConnectorError
    from app.integrations.ldap.connector import LdapConnector
    from app.modules.users.ldap_auth import resolve_mappings

    connector = await hub.get_connector(session, "ldap")  # desactivat → 409
    if not isinstance(connector, LdapConnector):  # defensa de registre
        raise Problem(500, "El hub ha resolt un connector inesperat per a «ldap»", "internal")

    trace: list[dict[str, Any]] = []
    profile: dict[str, Any] | None = None
    try:
        profile = await connector.authenticate(body.username, body.password, trace)
    except ConnectorError as exc:
        trace.append({"step": "directori", "ok": False, "detail": str(exc)})

    await _audit(session, authz_ctx.user.id, "config.ldap_test_login", body.username, ctx)
    await session.commit()

    if profile is None:
        return LdapTestLoginResponse(
            ok=False,
            steps=[LdapTestStep(**s) for s in trace],
            groups=[],
            matched_role=None,
            matched_department_names=[],
            email=None,
            name=None,
        )

    mappings = list((await session.execute(select(LdapGroupMapping))).scalars())
    role, department_ids = resolve_mappings(mappings, profile["groups"])

    # El pas que estalvia el desconcert «test verd però login vermell»:
    # un compte local amb contrasenya pròpia mai entra per l'AD.
    from app.modules.users.models import User

    profile_email = profile.get("email")
    local_account = None
    if profile_email:
        local_account = (
            await session.execute(select(User).where(User.email == profile_email))
        ).scalar_one_or_none()
    if local_account is not None and local_account.password_hash is not None:
        trace.append(
            {
                "step": "compte a LAGALia",
                "ok": False,
                "detail": (
                    f"«{profile_email}» és un compte local amb contrasenya pròpia: "
                    "el login LDAP no s'hi aplica (protecció dels comptes locals)"
                ),
            }
        )
        return LdapTestLoginResponse(
            ok=False,
            steps=[LdapTestStep(**s) for s in trace],
            groups=profile["groups"],
            matched_role=None,
            matched_department_names=[],
            email=profile_email,
            name=profile.get("name"),
        )
    trace.append(
        {
            "step": "compte a LAGALia",
            "ok": True,
            "detail": (
                "usuari de directori existent: s'actualitzarà al login"
                if local_account is not None
                else "nou: es crearà automàticament al primer login"
            ),
        }
    )
    names: list[str] = []
    if department_ids:
        names = list(
            (
                await session.execute(
                    select(Department.name).where(Department.id.in_(department_ids))
                )
            ).scalars()
        )
    trace.append(
        {
            "step": "regles de mapatge",
            "ok": role is not None,
            "detail": (
                f"rol: {role.value}" if role is not None else "cap grup de rol casat: accés denegat"
            ),
        }
    )
    return LdapTestLoginResponse(
        ok=role is not None,
        steps=[LdapTestStep(**s) for s in trace],
        groups=profile["groups"],
        matched_role=role,
        matched_department_names=names,
        email=profile.get("email"),
        name=profile.get("name"),
    )


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
# specs/field-mapping.md: overrides manuals del mapeig font → model, per a
# les TRES fonts: dataset de contractes (socrata), registre únic (rpc) i
# JSON de fases del portal (pscp, camins dins del document).

Source = Annotated[str, Path(min_length=2, max_length=20, pattern="^[a-z0-9_]+$")]
TargetField = Annotated[str, Path(min_length=1, max_length=100, pattern=r"^[a-z0-9_.]+$")]

_FLAT_SOURCE_PATTERN = r"^[a-z0-9_]{1,80}$"
_PATH_SOURCE_PATTERN = r"^~?[a-zA-Z0-9_.\[\]|]{1,200}$"


def _source_registry(source: str) -> dict[str, Any]:
    """target → (default, kind, label, phases|None). 404 si la font no és mapejable."""
    if source == "socrata":
        from app.integrations.socrata.mapping import CONTRACTOR_FIELDS, MAPPABLE_FIELDS

        return {
            t: (d.source, d.kind, d.label, None)
            for t, d in {**MAPPABLE_FIELDS, **CONTRACTOR_FIELDS}.items()
        }
    if source == "rpc":
        from app.integrations.socrata.sync_rpc import RPC_FIELDS

        return {t: (d.source, d.kind, d.label, None) for t, d in RPC_FIELDS.items()}
    if source == "execution":
        from app.integrations.socrata.sync_execution import EXECUTION_FIELDS

        return {t: (d.source, d.kind, d.label, None) for t, d in EXECUTION_FIELDS.items()}
    if source == "pscp":
        from app.integrations.pscp.extract import PSCP_FIELDS

        return {t: (d.path, d.kind, d.label, list(d.phases)) for t, d in PSCP_FIELDS.items()}
    raise Problem(404, "Aquesta font no té mapeig de camps", "not-found")


def _source_field_pattern(source: str) -> str:
    return _PATH_SOURCE_PATTERN if source == "pscp" else _FLAT_SOURCE_PATTERN


class FieldMappingRow(BaseModel):
    target_field: str
    label: str
    kind: str
    default_source_field: str
    source_field: str
    overridden: bool
    phases: list[str] | None = None


class FieldMappingUpdate(BaseModel):
    source_field: str = Field(min_length=1, max_length=200)


@router.get("/field-mappings/{source}", operation_id="listFieldMappings")
async def list_field_mappings(
    source: Source, session: SessionDep, _authz: ReadDep
) -> dict[str, list[FieldMappingRow]]:
    registry = _source_registry(source)
    from app.integrations.field_mappings import get_overrides

    overrides = await get_overrides(session, source)
    rows = [
        FieldMappingRow(
            target_field=target,
            label=label,
            kind=kind,
            default_source_field=default,
            source_field=overrides.get(target) or default,
            overridden=target in overrides,
            phases=phases,
        )
        for target, (default, kind, label, phases) in registry.items()
    ]
    return {"data": rows}


@router.get("/field-mappings/{source}/sample", operation_id="getFieldMappingSample")
async def get_field_mapping_sample(
    source: Source,
    file_code: Annotated[str, Query(min_length=1, max_length=100)],
    session: SessionDep,
    _authz: ReadDep,
    phase: Annotated[str | None, Query(max_length=30)] = None,
) -> dict[str, Any]:
    """Valors reals d'un expedient per triar camps. socrata/rpc: fila raw
    guardada (cap crida externa). pscp: JSON de fase aplanat a camins
    (descàrrega puntual de diagnòstic, com el healthcheck)."""
    _source_registry(source)  # 404 si no és mapejable
    from sqlalchemy import text as sql_text

    if source == "socrata":
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
            raise Problem(404, "Expedient sense fila sincronitzada", "not-found")
        return {"file_code": file_code, "fields": row.raw}

    if source == "rpc":
        minor = (
            await session.execute(
                sql_text(
                    "SELECT raw_award, raw_settlement FROM minor_contracts "
                    "WHERE file_code = :f LIMIT 1"
                ),
                {"f": file_code},
            )
        ).first()
        if minor is not None and (minor.raw_award or minor.raw_settlement):
            fields = {**(minor.raw_settlement or {}), **(minor.raw_award or {})}
            return {"file_code": file_code, "fields": fields}
        extension = (
            await session.execute(
                sql_text(
                    "SELECT e.raw FROM extensions e JOIN contracts c ON c.id = e.contract_id "
                    "WHERE c.file_code = :f AND e.raw IS NOT NULL LIMIT 1"
                ),
                {"f": file_code},
            )
        ).first()
        if extension is not None:
            return {"file_code": file_code, "fields": extension.raw}
        raise Problem(404, "Expedient sense registres RPC guardats", "not-found")

    if source == "execution":
        row = (
            await session.execute(
                sql_text(
                    "SELECT raw FROM contract_executions WHERE file_code = :f "
                    "ORDER BY id DESC LIMIT 1"
                ),
                {"f": file_code},
            )
        ).first()
        if row is None:
            raise Problem(404, "Expedient sense actuacions d'execució guardades", "not-found")
        return {"file_code": file_code, "fields": row.raw}

    # pscp: cal la URL de fase del contracte guardat.
    row = (
        await session.execute(
            sql_text(
                "SELECT phase_urls FROM contracts WHERE file_code = :f "
                "AND phase_urls IS NOT NULL ORDER BY id DESC LIMIT 1"
            ),
            {"f": file_code},
        )
    ).first()
    if row is None or not row.phase_urls:
        raise Problem(404, "Expedient sense URLs de fase guardades", "not-found")
    phase_urls: dict[str, str] = dict(row.phase_urls)
    phase_name = phase or next(iter(phase_urls))
    url = phase_urls.get(phase_name)
    if not url:
        available = ", ".join(phase_urls)
        raise Problem(404, f"Fase no disponible (té: {available})", "not-found")
    from app.integrations.base import ConnectorError
    from app.integrations.pscp.connector import PscpConnector
    from app.integrations.pscp.extract import flatten_paths

    try:
        connector = await hub.get_connector(session, "pscp")
    finally:
        await session.commit()
    if not isinstance(connector, PscpConnector):
        raise TypeError("El hub ha resolt un connector inesperat per a 'pscp'")
    try:
        async with connector.client() as client:
            payload = await client.fetch_phase(url)
    except ConnectorError as exc:
        raise Problem(502, "El portal no respon", "upstream", detail=str(exc)) from None
    return {"file_code": file_code, "phase": phase_name, "fields": flatten_paths(payload)}


@router.put("/field-mappings/{source}/{target_field}", operation_id="setFieldMapping")
async def set_field_mapping(
    source: Source,
    target_field: TargetField,
    body: FieldMappingUpdate,
    session: SessionDep,
    authz_ctx: WriteDep,
    ctx: ContextDep,
) -> FieldMappingRow:
    import re as _re

    registry = _source_registry(source)
    definition = registry.get(target_field)
    if definition is None:
        raise Problem(404, "Camp de destí desconegut", "not-found")
    if not _re.fullmatch(_source_field_pattern(source), body.source_field):
        raise Problem(422, "Camp font invàlid per a aquesta font", "validation")
    from sqlalchemy import text as sql_text

    await session.execute(
        sql_text(
            "INSERT INTO field_mappings (source, target_field, source_field, updated_by) "
            "VALUES (:s, :t, :f, :u) "
            "ON CONFLICT ON CONSTRAINT uq_field_mappings_source_target "
            "DO UPDATE SET source_field = :f, updated_by = :u, updated_at = now()"
        ),
        {"s": source, "t": target_field, "f": body.source_field, "u": authz_ctx.user.id},
    )
    await _audit(
        session,
        authz_ctx.user.id,
        "config.field_mapping_updated",
        f"{source}:{target_field}={body.source_field}",
        ctx,
    )
    await session.commit()
    default, kind, label, phases = definition
    return FieldMappingRow(
        target_field=target_field,
        label=label,
        kind=kind,
        default_source_field=default,
        source_field=body.source_field,
        overridden=body.source_field != default,
        phases=phases,
    )


@router.delete(
    "/field-mappings/{source}/{target_field}",
    operation_id="resetFieldMapping",
    status_code=204,
)
async def reset_field_mapping(
    source: Source,
    target_field: TargetField,
    session: SessionDep,
    authz_ctx: WriteDep,
    ctx: ContextDep,
) -> None:
    _source_registry(source)
    from sqlalchemy import text as sql_text

    await session.execute(
        sql_text("DELETE FROM field_mappings WHERE source = :s AND target_field = :t"),
        {"s": source, "t": target_field},
    )
    await _audit(
        session, authz_ctx.user.id, "config.field_mapping_reset", f"{source}:{target_field}", ctx
    )
    await session.commit()


_REMAP_JOBS = {
    # socrata i rpc: re-mapatge LOCAL des del raw guardat (cap crida externa).
    "socrata": ("sync.remap_contracts", {}),
    "rpc": ("sync.remap_rpc", {}),
    "execution": ("sync.remap_execution", {}),
    # pscp: re-enriquiment des de la font (els escalars surten del JSON viu).
    "pscp": ("enrich.batch", {"force": True, "download_documents": False, "trigger": "manual"}),
}


@router.post(
    "/field-mappings/{source}/actions/remap", operation_id="remapContracts", status_code=202
)
async def remap_contracts_action(
    source: Source, session: SessionDep, authz_ctx: ExecDep, ctx: ContextDep
) -> dict[str, Any]:
    """Re-aplica el mapeig vigent de la font a les dades guardades."""
    _source_registry(source)
    job_type, payload = _REMAP_JOBS[source]
    from app.jobs.service import enqueue_job

    job = await enqueue_job(
        session,
        job_type=job_type,
        payload=payload,
        created_by=authz_ctx.user.id or None,
        dedup_key=f"trigger:{job_type}",
    )
    await _audit(session, authz_ctx.user.id, "config.remap_triggered", source, ctx)
    await session.commit()
    return {"job_id": str(job.id), "job_type": job_type}
