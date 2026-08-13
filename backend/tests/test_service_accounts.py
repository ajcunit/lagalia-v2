"""Service accounts: gestió, scopes i accés de màquina (fase 1: lectura)."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.db import session_factory
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
            text("DELETE FROM service_accounts WHERE name LIKE :p"), {"p": f"SA {tag}%"}
        )
        await session.commit()


def _create(client: TestClient, headers: dict[str, str], tag: str, **overrides: Any) -> Any:
    payload = {"name": f"SA {tag}", "scopes": ["contracts:read"], **overrides}
    return client.post("/api/v1/service-accounts", json=payload, headers=headers)


async def test_management_and_key_only_once(
    api_client: TestClient, world: dict[str, Any]
) -> None:
    admin = login_headers(api_client, world["admin"].email)
    tag = world["tag"]

    # Només admin gestiona.
    denied = _create(api_client, login_headers(api_client, world["employee"].email), tag)
    assert denied.status_code == 403

    # Scope desconegut → 422.
    invalid = _create(api_client, admin, tag, scopes=["contracts:launch_rockets"])
    assert invalid.status_code == 422

    created = _create(api_client, admin, tag)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["key"].startswith("sk_")
    assert body["key_prefix"] == body["key"][:12]

    # La clau no torna a aparèixer; a BD només el hash.
    listing = api_client.get("/api/v1/service-accounts", headers=admin).json()["data"]
    mine = next(a for a in listing if a["id"] == body["id"])
    assert "key" not in mine
    async with session_factory() as session:
        stored = (
            await session.execute(
                text("SELECT key_hash FROM service_accounts WHERE id = :id"),
                {"id": body["id"]},
            )
        ).scalar_one()
    assert stored != body["key"] and len(stored) == 64


async def test_machine_access_scopes_and_lifecycle(
    api_client: TestClient, world: dict[str, Any]
) -> None:
    admin = login_headers(api_client, world["admin"].email)
    tag = world["tag"]
    created = _create(api_client, admin, tag, scopes=["contracts:read"]).json()
    machine = {"Authorization": f"Bearer {created['key']}"}

    # Amb scope: llegeix contractes (i amb vista global).
    listing = api_client.get(
        "/api/v1/contracts", params={"page[size]": 1, "view": "all"}, headers=machine
    )
    assert listing.status_code == 200, listing.text

    # Stats també és contracts:read.
    stats = api_client.get("/api/v1/contracts/stats", params={"view": "all"}, headers=machine)
    assert stats.status_code == 200

    # Sense l'scope corresponent: 403 (menors és un altre scope).
    denied = api_client.get("/api/v1/minor-contracts", headers=machine)
    assert denied.status_code == 403

    # Escriptures (sessió d'usuari): 401 en fase 1.
    write = api_client.post(
        "/api/v1/tasks",
        json={"title": "x", "due_date": "2030-01-01", "contract_id": 1},
        headers=machine,
    )
    assert write.status_code == 401

    # Clau desactivada → 401.
    api_client.patch(
        f"/api/v1/service-accounts/{created['id']}", json={"active": False}, headers=admin
    )
    assert api_client.get("/api/v1/contracts", headers=machine).status_code == 401

    # Reactivada però caducada → 401.
    api_client.patch(
        f"/api/v1/service-accounts/{created['id']}",
        json={"active": True, "expires_at": (datetime.now(UTC) - timedelta(days=1)).isoformat()},
        headers=admin,
    )
    assert api_client.get("/api/v1/contracts", headers=machine).status_code == 401

    # Revocació definitiva.
    deleted = api_client.delete(f"/api/v1/service-accounts/{created['id']}", headers=admin)
    assert deleted.status_code == 204
    assert api_client.get("/api/v1/contracts", headers=machine).status_code == 401

    # Clau inventada → 401 (mateix error que un JWT invàlid).
    fake = api_client.get(
        "/api/v1/contracts", headers={"Authorization": "Bearer sk_" + "x" * 43}
    )
    assert fake.status_code == 401
