"""Consulta i verificació d'audit_log (specs/audit-log-ui.md)."""

from datetime import UTC, datetime

import pytest

from app.core.db import session_factory
from app.modules.audit.models import AuditActorType, AuditLogEntry
from app.modules.audit.router import check_chain_entry
from app.modules.audit.service import record_audit
from tests.conftest import login_headers

pytestmark = pytest.mark.anyio


async def test_audit_log_api(api_client, make_user) -> None:  # type: ignore[no-untyped-def]
    admin_user = await make_user("admin")
    employee = await make_user("employee")
    admin = login_headers(api_client, admin_user.email)

    # El login d'aquest mateix test ja garanteix entrades auth.login.
    listing = api_client.get(
        "/api/v1/audit-log", params={"page[size]": 5, "filter[action]": "auth."}, headers=admin
    )
    assert listing.status_code == 200, listing.text
    body = listing.json()
    assert body["meta"]["total"] > 0
    assert all(e["action"].startswith("auth.") for e in body["data"])
    # Ordre per id desc i actor resolt per a usuaris.
    ids = [e["id"] for e in body["data"]]
    assert ids == sorted(ids, reverse=True)

    # Keyset: la segona pàgina continua sense solapar.
    if body["meta"]["next_cursor"]:
        page2 = api_client.get(
            "/api/v1/audit-log",
            params={
                "page[size]": 5,
                "filter[action]": "auth.",
                "page[cursor]": body["meta"]["next_cursor"],
            },
            headers=admin,
        )
        assert page2.status_code == 200
        assert all(e["id"] < min(ids) for e in page2.json()["data"])

    # Només admin (A2): employee → 403.
    denied = api_client.get(
        "/api/v1/audit-log", headers=login_headers(api_client, employee.email)
    )
    assert denied.status_code == 403

    # Verificació de la cadena sencera sobre la BD real.
    verify = api_client.post("/api/v1/audit-log/actions/verify", headers=admin)
    assert verify.status_code == 200, verify.text
    result = verify.json()
    assert result["status"] == "ok", result
    assert result["checked"] > 0


async def test_chain_tamper_detection() -> None:
    """Una manipulació es detecta sense haver d'esquivar el trigger de la BD:
    es comprova el helper amb l'entrada real i una còpia adulterada."""
    async with session_factory() as session:
        entry = await record_audit(
            session,
            actor_type=AuditActorType.SYSTEM,
            action="test.tamper_probe",
            success=True,
            details={"n": 1},
        )
        assert check_chain_entry(entry, None, is_first=True) is None

        tampered = AuditLogEntry(
            occurred_at=entry.occurred_at,
            actor_type=entry.actor_type,
            actor_id=entry.actor_id,
            action=entry.action,
            resource_type=entry.resource_type,
            resource_id=entry.resource_id,
            ip=entry.ip,
            user_agent=entry.user_agent,
            trace_id=entry.trace_id,
            details={"n": 2},  # contingut alterat, hash original
            success=entry.success,
            prev_hash=entry.prev_hash,
            entry_hash=entry.entry_hash,
        )
        assert check_chain_entry(tampered, None, is_first=True) is not None

        # Enllaç trencat: prev_hash que no encaixa amb l'anterior.
        assert check_chain_entry(entry, "0" * 64, is_first=False) is not None

        await session.rollback()


async def test_verify_datetime_roundtrip() -> None:
    """El payload canònic ha de sobreviure el viatge Python → Postgres → Python
    (microsegons i zona horària inclosos)."""
    async with session_factory() as session:
        entry = await record_audit(
            session,
            actor_type=AuditActorType.SYSTEM,
            action="test.roundtrip_probe",
            success=False,
            details={"quan": datetime.now(UTC).isoformat(), "text": "çàé€"},
            ip="192.168.10.44",
            trace_id="t-roundtrip",
        )
        await session.commit()
        entry_id = entry.id

    async with session_factory() as session:
        reloaded = await session.get(AuditLogEntry, entry_id)
        assert reloaded is not None
        assert check_chain_entry(reloaded, None, is_first=True) is None
