"""Webhooks sortints: outbox, signatura HMAC, reintents i API."""

import hashlib
import hmac
import json
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.db import session_factory
from app.modules.webhooks import service as webhook_service
from app.modules.webhooks.service import emit_event, publish_outbox, send_due_deliveries
from tests.conftest import login_headers


@pytest.fixture
async def world(make_user) -> AsyncIterator[dict[str, Any]]:  # type: ignore[no-untyped-def]
    tag = uuid4().hex[:8]
    data: dict[str, Any] = {"tag": tag}
    data["admin"] = await make_user("admin")
    data["employee"] = await make_user("employee")

    yield data

    async with session_factory() as session:
        await session.execute(
            text(
                "DELETE FROM webhook_deliveries WHERE webhook_id IN "
                "(SELECT id FROM outbound_webhooks WHERE name LIKE :p)"
            ),
            {"p": f"WH {tag}%"},
        )
        await session.execute(
            text("DELETE FROM outbound_webhooks WHERE name LIKE :p"), {"p": f"WH {tag}%"}
        )
        await session.execute(
            text("DELETE FROM outbox_events WHERE aggregate_id LIKE :p"), {"p": f"test-{tag}%"}
        )
        await session.commit()


async def test_crud_and_secret_only_once(api_client: TestClient, world: dict[str, Any]) -> None:
    admin = login_headers(api_client, world["admin"].email)
    tag = world["tag"]

    # employee: 403.
    denied = api_client.get(
        "/api/v1/webhooks", headers=login_headers(api_client, world["employee"].email)
    )
    assert denied.status_code == 403

    # URL http fora de desenvolupament es validaria; en dev s'accepta https i http.
    created = api_client.post(
        "/api/v1/webhooks",
        json={"name": f"WH {tag}", "url": "https://n8n.example/webhook/x", "events": ["*"]},
        headers=admin,
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["secret"].startswith("whsec_")
    webhook_id = body["id"]

    # El secret NO torna a aparèixer.
    listing = api_client.get("/api/v1/webhooks", headers=admin).json()["data"]
    mine = next(w for w in listing if w["id"] == webhook_id)
    assert "secret" not in mine
    assert mine["secret_is_set"] is True

    # PATCH desactiva.
    updated = api_client.patch(
        f"/api/v1/webhooks/{webhook_id}", json={"active": False}, headers=admin
    )
    assert updated.status_code == 200
    assert updated.json()["active"] is False

    deleted = api_client.delete(f"/api/v1/webhooks/{webhook_id}", headers=admin)
    assert deleted.status_code == 204


async def test_outbox_dispatch_signature_and_retry(
    api_client: TestClient, world: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    admin = login_headers(api_client, world["admin"].email)
    tag = world["tag"]

    created = api_client.post(
        "/api/v1/webhooks",
        json={
            "name": f"WH {tag} sig",
            "url": "https://receiver.example/hook",
            "events": ["test.event"],
        },
        headers=admin,
    ).json()
    secret = created["secret"]

    # Un altre webhook NO subscrit a aquest tipus.
    api_client.post(
        "/api/v1/webhooks",
        json={
            "name": f"WH {tag} altres",
            "url": "https://receiver.example/other",
            "events": ["contract.finished"],
        },
        headers=admin,
    )

    # Emissió transaccional + publicació.
    async with session_factory() as session:
        await emit_event(
            session,
            event_type="test.event",
            aggregate="test",
            aggregate_id=f"test-{tag}",
            data={"hello": "món"},
        )
        await session.commit()

    # Hermetisme: aparca les deliveries pendents alienes (BD de dev compartida);
    # el scheduler les reprendrà — només s'ajornen uns minuts.
    async with session_factory() as session:
        await session.execute(
            text(
                "UPDATE webhook_deliveries SET next_retry_at = now() + interval '15 minutes' "
                "WHERE status = 'pending' AND webhook_id NOT IN "
                "(SELECT id FROM outbound_webhooks WHERE name LIKE :p)"
            ),
            {"p": f"WH {tag}%"},
        )
        await session.commit()

    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        if request.url.path != "/hook":
            return httpx.Response(200)  # deliveries d'altres tests/webhooks
        first = len([r for r in captured if r.url.path == "/hook"]) == 1
        return httpx.Response(500 if first else 200)

    monkeypatch.setattr(
        webhook_service,
        "_client",
        lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    async with session_factory() as session:
        published = await publish_outbox(session)
        await send_due_deliveries(session)
        await session.commit()
    assert published >= 1

    # El nostre webhook ha rebut el 500 i té reintent programat.
    async with session_factory() as session:
        status_row = (
            (
                await session.execute(
                    text("SELECT status, attempts FROM webhook_deliveries WHERE webhook_id = :w"),
                    {"w": created["id"]},
                )
            )
            .mappings()
            .one()
        )
    assert status_row["status"] == "pending"
    assert status_row["attempts"] == 1

    # Reintent: forcem el venciment i tornem a despatxar.
    async with session_factory() as session:
        await session.execute(
            text("UPDATE webhook_deliveries SET next_retry_at = now() WHERE webhook_id = :w"),
            {"w": created["id"]},
        )
        await session.commit()
    async with session_factory() as session:
        await send_due_deliveries(session)
        await session.commit()

    # Només el webhook subscrit al tipus ha rebut /hook; signatura verificable.
    hook_requests = [r for r in captured if r.url.path == "/hook"]
    assert len(hook_requests) == 2
    request = hook_requests[-1]
    assert request.url.host == "receiver.example"
    timestamp = request.headers["X-Timestamp"]
    expected = hmac.new(
        secret.encode(), f"{timestamp}.".encode() + request.content, hashlib.sha256
    ).hexdigest()
    assert request.headers["X-Signature"] == f"sha256={expected}"
    payload = json.loads(request.content)
    assert payload["type"] == "test.event"
    assert payload["data"] == {"hello": "món"}
    assert payload["subject"] == f"test/test-{tag}"

    # Deliveries consultables.
    deliveries = api_client.get(
        f"/api/v1/webhooks/{created['id']}/deliveries", headers=admin
    ).json()["data"]
    assert deliveries[0]["status"] == "delivered"
    assert deliveries[0]["attempts"] == 2
