import base64

import pytest
from pydantic import ValidationError

from app.core.config import Settings

VALID_ENCRYPTION_KEY = base64.b64encode(b"\x01" * 32).decode()
VALID_SECRET_KEY = "prou-llarga-per-passar-la-validacio-0123456789"


def _settings(**overrides: str) -> Settings:
    values = {
        "secret_key": VALID_SECRET_KEY,
        "encryption_key": VALID_ENCRYPTION_KEY,
        **overrides,
    }
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


def test_fails_without_secret_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SECRET_KEY", raising=False)

    with pytest.raises(ValidationError, match="secret_key"):
        Settings(_env_file=None, encryption_key=VALID_ENCRYPTION_KEY)


def test_fails_without_encryption_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ENCRYPTION_KEY", raising=False)

    with pytest.raises(ValidationError, match="encryption_key"):
        Settings(_env_file=None, secret_key=VALID_SECRET_KEY)


def test_fails_with_short_secret_key() -> None:
    with pytest.raises(ValidationError, match="32"):
        _settings(secret_key="curta")


def test_fails_with_non_base64_encryption_key() -> None:
    with pytest.raises(ValidationError, match="base64"):
        _settings(encryption_key="això-no-és-base64!!!")


def test_fails_with_wrong_length_encryption_key() -> None:
    with pytest.raises(ValidationError, match="32 bytes"):
        _settings(encryption_key=base64.b64encode(b"\x01" * 16).decode())


def test_defaults_are_safe() -> None:
    settings = _settings()

    assert settings.environment == "development"
    assert settings.debug is False
    assert settings.log_format == "json"


def test_secrets_never_leak_in_repr() -> None:
    settings = _settings()

    assert VALID_SECRET_KEY not in repr(settings)
    assert VALID_ENCRYPTION_KEY not in repr(settings)


async def test_connectors_config_api(api_client, make_user) -> None:  # type: ignore[no-untyped-def]
    from tests.conftest import login_headers

    admin_user = await make_user("admin")
    employee = await make_user("employee")
    admin = login_headers(api_client, admin_user.email)

    # Llistat: hi ha smtp registrat i les credencials mai porten valor.
    listing = api_client.get("/api/v1/connectors", headers=admin)
    assert listing.status_code == 200, listing.text
    smtp = next(c for c in listing.json()["data"] if c["slug"] == "smtp")
    assert set(smtp["credentials"]) == {"username", "password"}
    assert all(isinstance(v, bool) for v in smtp["credentials"].values())

    # employee llegeix però no escriu.
    assert (
        api_client.get(
            "/api/v1/connectors", headers=login_headers(api_client, employee.email)
        ).status_code
        == 200
    )
    denied = api_client.patch(
        "/api/v1/connectors/smtp",
        json={"enabled": True},
        headers=login_headers(api_client, employee.email),
    )
    assert denied.status_code == 403

    # Config validada contra el manifest; credencials write-only.
    bad = api_client.patch(
        "/api/v1/connectors/smtp", json={"config": {"inventada": 1}}, headers=admin
    )
    assert bad.status_code == 422
    updated = api_client.put(
        "/api/v1/connectors/smtp/credentials",
        json={"credentials": {"username": "u", "password": "p"}},
        headers=admin,
    )
    assert updated.status_code == 200
    assert updated.json()["credentials"] == {"username": True, "password": True}
    assert '"u"' not in updated.text and '"p"' not in updated.text

    # Correu de prova: mai tomba l'API (connector desactivat/sense host →
    # failed estructurat); employee → 403.
    test_mail = api_client.post("/api/v1/connectors/smtp/actions/send-test-email", headers=admin)
    assert test_mail.status_code == 200, test_mail.text
    assert test_mail.json()["status"] == "failed"
    assert (
        api_client.post(
            "/api/v1/connectors/smtp/actions/send-test-email",
            headers=login_headers(api_client, employee.email),
        ).status_code
        == 403
    )

    # Els paràmetres coneguts surten encara que no existeixin a la BD.
    listing_before = api_client.get("/api/v1/settings", headers=admin).json()["data"]
    recipients = next(s for s in listing_before if s["key"] == "reports.audit_recipients")
    assert recipients["is_set"] is False and recipients["placeholder"]

    # Paràmetres: secret emmascarat.
    put = api_client.put(
        "/api/v1/settings/test.config_api_secret",
        json={"value": "supersecret", "is_secret": True},
        headers=admin,
    )
    assert put.status_code == 200
    assert put.json()["value"] is None and put.json()["is_set"] is True
    listed = api_client.get("/api/v1/settings", headers=admin).json()["data"]
    row = next(s for s in listed if s["key"] == "test.config_api_secret")
    assert row["value"] is None

    from sqlalchemy import text as sql_text

    from app.core.db import session_factory

    async with session_factory() as session:
        await session.execute(sql_text("DELETE FROM settings WHERE key = 'test.config_api_secret'"))
        await session.execute(
            sql_text(
                "DELETE FROM connector_credentials WHERE connector_id IN "
                "(SELECT id FROM connectors WHERE slug = 'smtp')"
            )
        )
        await session.commit()


def test_trusted_proxy_ips_parsing() -> None:
    """La llista accepta comes o JSON; buida = no confiar en cap proxy."""
    from app.core.config import Settings

    common = {"secret_key": VALID_SECRET_KEY, "encryption_key": VALID_ENCRYPTION_KEY}
    assert Settings(trusted_proxy_ips="", **common).trusted_proxy_ips == []  # type: ignore[arg-type]
    assert Settings(trusted_proxy_ips="10.0.0.1, 10.0.0.2", **common).trusted_proxy_ips == [
        "10.0.0.1",
        "10.0.0.2",
    ]  # type: ignore[arg-type]
    assert Settings(trusted_proxy_ips=["10.0.0.3"], **common).trusted_proxy_ips == ["10.0.0.3"]


def test_client_ip_only_trusts_declared_proxies(monkeypatch: pytest.MonkeyPatch) -> None:
    """X-Forwarded-For només val si la connexió ve d'un proxy declarat:
    altrament qualsevol podria falsificar la seva IP (docs/06 §5)."""
    from starlette.requests import Request

    from app.core.config import settings
    from app.modules.users.dependencies import client_ip

    def make_request(peer: str, forwarded: str | None) -> Request:
        headers = []
        if forwarded is not None:
            headers.append((b"x-forwarded-for", forwarded.encode()))
        return Request(
            {
                "type": "http",
                "headers": headers,
                "client": (peer, 12345),
            }
        )

    # Sense proxys declarats: la capçalera s'ignora sempre.
    monkeypatch.setattr(settings, "trusted_proxy_ips", [])
    assert client_ip(make_request("203.0.113.9", "1.2.3.4")) == "203.0.113.9"

    # Amb el proxy declarat: es pren el primer valor de la cadena.
    monkeypatch.setattr(settings, "trusted_proxy_ips", ["10.0.0.1"])
    assert client_ip(make_request("10.0.0.1", "198.51.100.7, 10.0.0.1")) == "198.51.100.7"

    # Una IP que no és el proxy no pot falsificar la capçalera.
    assert client_ip(make_request("203.0.113.9", "198.51.100.7")) == "203.0.113.9"

    # Capçalera amb escombraries: es cau a la IP de la connexió.
    assert client_ip(make_request("10.0.0.1", "no-es-una-ip")) == "10.0.0.1"
