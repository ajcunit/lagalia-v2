"""Historial i llançament de sincronitzacions (specs/sync-admin.md)."""

import pytest
from sqlalchemy import text

from app.core.db import session_factory
from tests.conftest import login_headers

pytestmark = pytest.mark.anyio


async def _cleanup_jobs(job_ids: list[str]) -> None:
    """Els jobs de test s'encuen a la cua de test (mai es consumeixen):
    s'esborren perquè el dedup_key no bloquegi llançaments reals."""
    if not job_ids:
        return
    async with session_factory() as session:
        await session.execute(
            text("DELETE FROM jobs WHERE id = ANY(CAST(:ids AS uuid[]))"), {"ids": job_ids}
        )
        await session.commit()


async def test_sync_admin_api(api_client, make_user) -> None:  # type: ignore[no-untyped-def]
    admin_user = await make_user("admin")
    employee = await make_user("employee")
    admin = login_headers(api_client, admin_user.email)
    created_jobs: list[str] = []

    try:
        # Historial: hi ha runs reals a la BD de dev; keyset per id desc.
        listing = api_client.get("/api/v1/sync-runs", params={"page[size]": 5}, headers=admin)
        assert listing.status_code == 200, listing.text
        body = listing.json()
        ids = [r["id"] for r in body["data"]]
        assert ids == sorted(ids, reverse=True)
        if body["meta"]["next_cursor"]:
            page2 = api_client.get(
                "/api/v1/sync-runs",
                params={"page[size]": 5, "page[cursor]": body["meta"]["next_cursor"]},
                headers=admin,
            )
            assert page2.status_code == 200
            assert all(r["id"] < min(ids) for r in page2.json()["data"])

        # Filtre per kind.
        filtered = api_client.get(
            "/api/v1/sync-runs", params={"filter[kind]": "contracts"}, headers=admin
        )
        assert filtered.status_code == 200
        assert all(r["kind"] == "contracts" for r in filtered.json()["data"])

        # Items d'un run existent (si n'hi ha) i 404 per a un d'inexistent.
        if ids:
            items = api_client.get(f"/api/v1/sync-runs/{ids[0]}/items", headers=admin)
            assert items.status_code == 200
        assert api_client.get("/api/v1/sync-runs/999999999/items", headers=admin).status_code == 404

        # employee: sense sync:read ni sync:execute → 403.
        emp = login_headers(api_client, employee.email)
        assert api_client.get("/api/v1/sync-runs", headers=emp).status_code == 403
        assert (
            api_client.post(
                "/api/v1/sync-runs/actions/trigger", json={"kind": "cpv"}, headers=emp
            ).status_code
            == 403
        )

        # Llançament: encua el job correcte; el dedup fa que el segon sigui 409.
        first = api_client.post(
            "/api/v1/sync-runs/actions/trigger", json={"kind": "cpv"}, headers=admin
        )
        assert first.status_code == 202, first.text
        assert first.json()["job_type"] == "sync.cpv"
        created_jobs.append(first.json()["job_id"])

        second = api_client.post(
            "/api/v1/sync-runs/actions/trigger", json={"kind": "cpv"}, headers=admin
        )
        assert second.status_code == 409

        # kind invàlid → 422 (validació del contracte).
        bad = api_client.post(
            "/api/v1/sync-runs/actions/trigger", json={"kind": "inventat"}, headers=admin
        )
        assert bad.status_code == 422

        # El trigger del payload el fixa el servidor (manual per a usuaris).
        async with session_factory() as session:
            payload = (
                await session.execute(
                    text("SELECT payload FROM jobs WHERE id = :id"),
                    {"id": created_jobs[0]},
                )
            ).scalar_one()
        assert payload["trigger"] == "manual"
    finally:
        await _cleanup_jobs(created_jobs)
