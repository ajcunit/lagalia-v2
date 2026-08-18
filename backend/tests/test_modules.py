"""Mòduls activables (specs/module-flags.md)."""

import pytest
from fastapi.testclient import TestClient

from app.core import modules
from tests.conftest import MakeUser, login_headers

pytestmark = pytest.mark.anyio


def test_module_for_path() -> None:
    assert modules.module_for_path("/api/v1/chat/threads") == "chat"
    assert modules.module_for_path("/api/v1/ai/analyses/stream") == "analyst"
    assert modules.module_for_path("/api/v1/audit/red-flags") == "risk_audit"
    # /audit-log és el nucli (auditoria de seguretat): mai es talla.
    assert modules.module_for_path("/api/v1/audit-log") is None
    assert modules.module_for_path("/api/v1/contracts/12") is None
    assert modules.module_for_path("/api/v1/settings") is None
    assert modules.module_for_path("/health") is None


def test_parse_disabled_ignores_unknown_keys() -> None:
    assert modules.parse_disabled('["chat", "contracts", "inventat"]') == frozenset({"chat"})
    assert modules.parse_disabled(["plan", "webhooks"]) == frozenset({"plan", "webhooks"})
    assert modules.parse_disabled(None) == frozenset()
    assert modules.parse_disabled("no és json") == frozenset()


async def test_disabled_module_cuts_api_and_shows_in_permissions(
    api_client: TestClient, make_user: MakeUser
) -> None:
    admin = await make_user("admin")
    headers = login_headers(api_client, admin.email)

    def put_disabled(value: list[str]) -> None:
        response = api_client.put(
            "/api/v1/settings/modules.disabled", json={"value": value}, headers=headers
        )
        assert response.status_code == 200, response.text

    try:
        put_disabled(["chat", "nucli-inventat"])

        cut = api_client.get("/api/v1/chat/threads", headers=headers)
        assert cut.status_code == 403
        assert "module-disabled" in cut.json()["type"]

        permissions = api_client.get("/api/v1/me/permissions", headers=headers)
        assert permissions.status_code == 200
        # La clau desconeguda s'ha descartat al PUT.
        assert permissions.json()["disabled_modules"] == ["chat"]

        # El nucli continua intacte.
        core = api_client.get("/api/v1/settings", headers=headers)
        assert core.status_code == 200
    finally:
        put_disabled([])

    restored = api_client.get("/api/v1/chat/threads", headers=headers)
    assert restored.status_code == 200
