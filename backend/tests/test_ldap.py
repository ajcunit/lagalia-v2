"""Autenticació LDAP/AD (specs/ldap-auth.md): filtre escapat, transport
segur obligatori, resolució de mapatges, provisió automàtica i fallback
local quan l'AD cau. El directori es simula (FakeConnector): cap test no
necessita un AD real."""

from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.integrations.base import ConnectorError
from app.integrations.ldap.connector import (
    LdapConnector,
    build_user_filter,
    parse_server_address,
    upn_candidates,
)
from app.modules.users import ldap_auth
from app.modules.users.models import LdapGroupMapping, UserRole
from tests.conftest import TEST_PASSWORD, MakeUser, login_headers

pytestmark = pytest.mark.anyio


# ─────────────────────────── unitat: connector ───────────────────────────


def test_build_user_filter_escapes_hostile_input() -> None:
    hostile = "adm*)(objectClass=*)(\\x="
    built = build_user_filter(hostile)
    # RFC 4515: els metacaràcters queden escapats, mai en cru.
    assert "\\2a" in built and "\\28" in built and "\\29" in built and "\\5c" in built
    assert "*)(objectClass" not in built
    assert built.count("(|") == 1


def test_parse_server_address() -> None:
    # Sense esquema s'assumeix LDAPS; el port de la URL mana sobre la config.
    assert parse_server_address("ad.cunit.local", 636, False) == ("ad.cunit.local", 636, True)
    assert parse_server_address("ldaps://10.0.0.1", 636, False) == ("10.0.0.1", 636, True)
    assert parse_server_address("ldaps://ad:3269", 636, False) == ("ad", 3269, True)
    assert parse_server_address("ldap://10.0.0.1", 389, True) == ("10.0.0.1", 389, False)
    with pytest.raises(ConnectorError, match="ldaps"):
        parse_server_address("ldap://10.0.0.1", 389, False)  # en clar sense StartTLS
    with pytest.raises(ConnectorError):
        parse_server_address("", 636, False)


def test_upn_candidates() -> None:
    # Login amb el correu però UPN d'AD amb un altre sufix: es proven tots dos.
    assert upn_candidates("algu@cunit.cat", "@ajcunit.local") == [
        "algu@cunit.cat",
        "algu@ajcunit.local",
    ]
    assert upn_candidates("usuari", "ajuntament.local") == [
        "usuari",
        "usuari@ajuntament.local",
    ]
    assert upn_candidates("algu@cunit.cat", "@cunit.cat") == ["algu@cunit.cat"]
    assert upn_candidates("usuari", "") == ["usuari"]


async def test_insecure_transport_rejected() -> None:
    connector = LdapConnector(
        {"server_url": "ldap://ad.cunit.local", "base_dn": "DC=x", "starttls": False},
        {"bind_dn": "svc", "bind_password": "s"},
    )
    with pytest.raises(ConnectorError, match="ldaps"):
        await connector.authenticate("algu@cunit.cat", "contrasenya")


async def test_empty_password_rejected_before_network() -> None:
    # Un bind anònim "encertaria": es refusa abans de tocar la xarxa
    # (el host és inexistent: si s'hi connectés, petaria).
    connector = LdapConnector(
        {"server_url": "ldaps://no-existeix.invalid", "base_dn": "DC=x", "starttls": False},
        {"bind_dn": "svc", "bind_password": "s"},
    )
    assert await connector.authenticate("algu@cunit.cat", "   ") is None
    assert await connector.authenticate("", "contrasenya") is None


# ─────────────────────────── unitat: mapatges ───────────────────────────


def _mapping(ad_group: str, role: UserRole | None = None, dept: int | None = None) -> Any:
    return LdapGroupMapping(ad_group=ad_group, role=role, department_id=dept)


def test_resolve_mappings_highest_role_and_department_union() -> None:
    mappings = [
        _mapping("CN=LAGALIA-Consulta,OU=Grups,DC=cunit,DC=local", role=UserRole.EMPLOYEE),
        _mapping("lagalia-gestio", role=UserRole.PROCUREMENT_MANAGER),
        _mapping("CN=LAGALIA-DEP-TIC,OU=Grups,DC=cunit,DC=local", dept=11),
        _mapping("lagalia-dep-urbanisme", dept=22),
        _mapping("lagalia-admins", role=UserRole.ADMIN),
    ]
    groups = [
        "CN=LAGALIA-Consulta,OU=Grups,DC=cunit,DC=local",
        "CN=LAGALIA-Gestio,OU=Grups,DC=cunit,DC=local",  # casa pel CN, case-insensitive
        "CN=LAGALIA-DEP-TIC,OU=Grups,DC=cunit,DC=local",
        "CN=Lagalia-Dep-Urbanisme,OU=Grups,DC=cunit,DC=local",
    ]
    role, department_ids = ldap_auth.resolve_mappings(mappings, groups)
    assert role == UserRole.PROCUREMENT_MANAGER  # el més alt dels casats, no admin
    assert department_ids == {11, 22}


def test_resolve_mappings_without_role_group_gives_no_access() -> None:
    mappings = [_mapping("lagalia-dep-tic", dept=11)]
    role, department_ids = ldap_auth.resolve_mappings(
        mappings, ["CN=LAGALIA-DEP-TIC,OU=Grups,DC=cunit,DC=local"]
    )
    assert role is None  # departament sol no dona accés
    assert department_ids == {11}


# ─────────────────────────── integració: login ───────────────────────────


class FakeConnector:
    """Simula LdapConnector.authenticate; el perfil el fixa cada test."""

    def __init__(self, profile: dict[str, Any] | None = None, down: bool = False) -> None:
        self.profile = profile
        self.down = down

    async def authenticate(self, identifier: str, password: str) -> dict[str, Any] | None:
        if self.down:
            raise ConnectorError("directori inabastable")
        if password != "Directori-AD-123":
            return None
        return self.profile


def _patch_connector(monkeypatch: pytest.MonkeyPatch, connector: FakeConnector | None) -> None:
    async def _fake_resolve(session: Any) -> FakeConnector | None:
        return connector

    monkeypatch.setattr(ldap_auth, "_resolve_connector", _fake_resolve)


@pytest.fixture
async def ldap_fixture() -> Any:
    """Departament + regles (rol i departament) amb neteja completa."""
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    async with engine.begin() as conn:
        dept_id = (
            await conn.execute(
                text(
                    "INSERT INTO departments (code, name) "
                    "VALUES (:code, 'Departament LDAP') RETURNING id"
                ),
                {"code": f"LDP-{uuid4().hex[:8]}"},
            )
        ).scalar_one()
        role_group = f"lagalia-gestio-{uuid4().hex[:6]}"
        dept_group = f"lagalia-dep-{uuid4().hex[:6]}"
        await conn.execute(
            text(
                "INSERT INTO ldap_group_mappings (ad_group, role) "
                "VALUES (:g, 'procurement_manager')"
            ),
            {"g": role_group},
        )
        await conn.execute(
            text("INSERT INTO ldap_group_mappings (ad_group, department_id) VALUES (:g, :d)"),
            {"g": dept_group, "d": dept_id},
        )
    email = f"ldap-{uuid4().hex[:10]}@cunit.cat"
    yield {
        "dept_id": dept_id,
        "role_group": role_group,
        "dept_group": dept_group,
        "email": email,
    }
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM users WHERE email = :e"), {"e": email})
        await conn.execute(
            text("DELETE FROM ldap_group_mappings WHERE ad_group IN (:a, :b)"),
            {"a": role_group, "b": dept_group},
        )
        await conn.execute(text("DELETE FROM departments WHERE id = :id"), {"id": dept_id})
    await engine.dispose()


def _profile(fixture: dict[str, Any]) -> dict[str, Any]:
    return {
        "dn": "CN=Prova LDAP,OU=Usuaris,DC=cunit,DC=local",
        "name": "Prova LDAP",
        "email": fixture["email"],
        "sam": "provaldap",
        "groups": [
            f"CN={fixture['role_group']},OU=Grups,DC=cunit,DC=local",
            f"CN={fixture['dept_group']},OU=Grups,DC=cunit,DC=local",
        ],
    }


async def test_ldap_login_provisions_role_and_departments(
    api_client: TestClient, ldap_fixture: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_connector(monkeypatch, FakeConnector(profile=_profile(ldap_fixture)))

    response = api_client.post(
        "/api/v1/auth/login",
        json={"email": ldap_fixture["email"], "password": "Directori-AD-123"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["access_token"]

    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    async with engine.connect() as conn:
        row = (
            await conn.execute(
                text("SELECT id, role, password_hash FROM users WHERE email = :e"),
                {"e": ldap_fixture["email"]},
            )
        ).one()
        departments = [
            r.department_id
            for r in await conn.execute(
                text("SELECT department_id FROM user_departments WHERE user_id = :u"),
                {"u": row.id},
            )
        ]
        provision = (
            await conn.execute(
                text(
                    "SELECT success FROM audit_log WHERE action = 'auth.ldap_provision' "
                    "AND details->>'email' = :e ORDER BY id DESC LIMIT 1"
                ),
                {"e": ldap_fixture["email"]},
            )
        ).scalar_one_or_none()
    await engine.dispose()

    assert row.role == "procurement_manager"  # lint-ok: assercio de fila, no authz
    assert row.password_hash is None  # usuari de directori: mai contrasenya local
    assert departments == [ldap_fixture["dept_id"]]
    assert provision is True

    # Contrasenya incorrecta contra l'AD → 401 (el fake només accepta la bona).
    denied = api_client.post(
        "/api/v1/auth/login",
        json={"email": ldap_fixture["email"], "password": "Una-altra-cosa-999"},
    )
    assert denied.status_code == 401


async def test_ldap_login_without_role_group_denied(
    api_client: TestClient, ldap_fixture: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    profile = _profile(ldap_fixture)
    profile["groups"] = [f"CN={ldap_fixture['dept_group']},OU=Grups,DC=cunit,DC=local"]
    _patch_connector(monkeypatch, FakeConnector(profile=profile))

    response = api_client.post(
        "/api/v1/auth/login",
        json={"email": ldap_fixture["email"], "password": "Directori-AD-123"},
    )
    assert response.status_code == 401  # l'AD autentica, la plataforma no


async def test_ad_down_keeps_local_login_working(
    api_client: TestClient, make_user: MakeUser, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_connector(monkeypatch, FakeConnector(down=True))
    local = await make_user("employee")

    response = api_client.post(
        "/api/v1/auth/login", json={"email": local.email, "password": TEST_PASSWORD}
    )
    assert response.status_code == 200  # el login local no depèn de l'AD

    unknown = api_client.post(
        "/api/v1/auth/login",
        json={"email": f"nou-{uuid4().hex[:8]}@cunit.cat", "password": "Directori-AD-123"},
    )
    assert unknown.status_code == 401  # LDAP caigut → refús net, mai un 500


async def test_local_user_with_password_never_touches_ldap(
    api_client: TestClient, make_user: MakeUser, monkeypatch: pytest.MonkeyPatch
) -> None:
    local = await make_user("employee")
    profile = {
        "dn": "CN=X",
        "name": "Suplantació",
        "email": local.email,
        "sam": "x",
        "groups": [],
    }
    _patch_connector(monkeypatch, FakeConnector(profile=profile))

    # La contrasenya del directori NO obre un compte local amb hash propi.
    response = api_client.post(
        "/api/v1/auth/login", json={"email": local.email, "password": "Directori-AD-123"}
    )
    assert response.status_code == 401


async def test_ldap_test_login_action(
    api_client: TestClient,
    make_user: MakeUser,
    ldap_fixture: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Diagnòstic d'admin: passos, grups i regles casades, sense tocar usuaris."""
    from app.integrations import hub

    admin = await make_user("admin")
    headers = login_headers(api_client, admin.email)
    profile = _profile(ldap_fixture)

    class FakeLdap(LdapConnector):
        async def authenticate(
            self, identifier: str, password: str, trace: list[dict[str, Any]] | None = None
        ) -> dict[str, Any] | None:
            if trace is not None:
                trace.append({"step": "bind d'usuari", "ok": True, "detail": identifier})
            return profile

    async def fake_get_connector(session: Any, slug: str) -> Any:
        assert slug == "ldap"
        return FakeLdap({}, {})

    monkeypatch.setattr(hub, "get_connector", fake_get_connector)

    response = api_client.post(
        "/api/v1/connectors/ldap/actions/test-login",
        json={"username": "provaldap", "password": "Directori-AD-123"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is True
    assert body["matched_role"] == "procurement_manager"
    assert body["matched_department_names"] == ["Departament LDAP"]
    assert body["groups"] == profile["groups"]
    assert body["steps"][-1]["step"] == "regles de mapatge"
    # El diagnòstic no provisiona: l'usuari del perfil no existeix.
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    async with engine.connect() as conn:
        count = (
            await conn.execute(
                text("SELECT count(*) FROM users WHERE email = :e"),
                {"e": ldap_fixture["email"]},
            )
        ).scalar_one()
    await engine.dispose()
    assert count == 0

    # Perfil que resol al correu d'un compte local amb contrasenya: el
    # diagnòstic ho ha d'avisar (el login LDAP no s'hi aplicarà mai).
    profile["email"] = admin.email
    warned = api_client.post(
        "/api/v1/connectors/ldap/actions/test-login",
        json={"username": "provaldap", "password": "Directori-AD-123"},
        headers=headers,
    )
    assert warned.status_code == 200
    body = warned.json()
    assert body["ok"] is False
    assert body["steps"][-1]["step"] == "compte a LAGALia"
    assert body["matched_role"] is None


# ─────────────────────────── API de regles ───────────────────────────


async def test_mapping_rules_crud(api_client: TestClient, make_user: MakeUser) -> None:
    admin = await make_user("admin")
    headers = login_headers(api_client, admin.email)
    group = f"lagalia-crud-{uuid4().hex[:6]}"

    created = api_client.post(
        "/api/v1/ldap/group-mappings",
        json={"ad_group": group, "role": "dept_manager"},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    mapping_id = created.json()["id"]
    assert created.json()["role"] == "dept_manager"

    # Duplicat (case-insensitive) → 409.
    duplicate = api_client.post(
        "/api/v1/ldap/group-mappings",
        json={"ad_group": group.upper(), "role": "employee"},
        headers=headers,
    )
    assert duplicate.status_code == 409

    # Regla amb rol I departament alhora → 422.
    both = api_client.post(
        "/api/v1/ldap/group-mappings",
        json={"ad_group": f"x-{uuid4().hex[:6]}", "role": "employee", "department_id": 1},
        headers=headers,
    )
    assert both.status_code == 422

    # Departament inexistent → 404.
    missing = api_client.post(
        "/api/v1/ldap/group-mappings",
        json={"ad_group": f"x-{uuid4().hex[:6]}", "department_id": 999999999},
        headers=headers,
    )
    assert missing.status_code == 404

    listed = api_client.get("/api/v1/ldap/group-mappings", headers=headers)
    assert listed.status_code == 200
    assert any(row["id"] == mapping_id for row in listed.json()["data"])

    deleted = api_client.delete(f"/api/v1/ldap/group-mappings/{mapping_id}", headers=headers)
    assert deleted.status_code == 204
