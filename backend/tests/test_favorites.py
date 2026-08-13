"""Favorits (specs/favorites.md): propietat estricta i snapshot sense tocar contracts."""

from typing import Any

import pytest
from sqlalchemy import text

from app.core.db import session_factory
from tests.conftest import login_headers

pytestmark = pytest.mark.anyio


async def _count_contracts() -> int:
    async with session_factory() as session:
        return (await session.execute(text("SELECT count(*) FROM contracts"))).scalar_one()


async def test_favorites_flow(api_client, make_user, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    owner = await make_user("employee")
    other = await make_user("employee")
    mine = login_headers(api_client, owner.email)
    theirs = login_headers(api_client, other.email)

    # El snapshot no depèn de la xarxa al test: substituïm la consulta al registre.
    from app.modules import favorites as favorites_pkg

    async def fake_public_contract(file_code: str, session: Any, authz_ctx: Any) -> dict[str, Any]:
        if file_code == "NO-EXISTEIX":
            from app.core.problems import Problem

            raise Problem(404, "Expedient desconegut al registre públic", "not-found")
        return {
            "data": [
                {
                    "file_code": file_code,
                    "lot": "",
                    "status": "Formalitzat",
                    "subject": "Servei de prova",
                    "awarding_body": "Ajuntament de Prova",
                    "published_at": "2026-01-15T10:00:00",
                    "budget_vat": "12100.00",
                    "award_amount": "10000.00",
                    "links": {},
                    "phase_urls": None,
                    "contractor": {"name": "Empresa SA", "nif": "A00000000"},
                }
            ]
        }

    monkeypatch.setattr(favorites_pkg.router, "get_public_contract", fake_public_contract)

    contracts_before = await _count_contracts()

    # Carpeta pròpia; color validat.
    bad_color = api_client.post(
        "/api/v1/folders", json={"name": "X", "color": "fúcsia"}, headers=mine
    )
    assert bad_color.status_code == 422
    folder = api_client.post(
        "/api/v1/folders",
        json={"name": "Licitacions de neteja", "color": "teal"},
        headers=mine,
    )
    assert folder.status_code == 201, folder.text
    folder_id = folder.json()["id"]

    # L'altre usuari no la veu ni la pot tocar (404, mai 403).
    their_folders = api_client.get("/api/v1/folders", headers=theirs).json()["data"]
    assert folder_id not in [f["id"] for f in their_folders]
    assert (
        api_client.patch(
            f"/api/v1/folders/{folder_id}", json={"name": "seva"}, headers=theirs
        ).status_code
        == 404
    )

    # Afegir favorit: desa snapshot; duplicat → 409; inexistent → 404.
    added = api_client.post(
        f"/api/v1/folders/{folder_id}/favorites", json={"file_code": "77/2026"}, headers=mine
    )
    assert added.status_code == 201, added.text
    assert added.json()["snapshot"][0]["contractor"]["name"] == "Empresa SA"
    favorite_id = added.json()["id"]
    assert (
        api_client.post(
            f"/api/v1/folders/{folder_id}/favorites", json={"file_code": "77/2026"}, headers=mine
        ).status_code
        == 409
    )
    assert (
        api_client.post(
            f"/api/v1/folders/{folder_id}/favorites",
            json={"file_code": "NO-EXISTEIX"},
            headers=mine,
        ).status_code
        == 404
    )

    # LA GARANTIA: contracts no ha crescut.
    assert await _count_contracts() == contracts_before

    # Llistat amb comptador; treure; esborrar carpeta en cascada.
    folders = api_client.get("/api/v1/folders", headers=mine).json()["data"]
    assert next(f for f in folders if f["id"] == folder_id)["favorites_count"] == 1
    assert (
        api_client.delete(
            f"/api/v1/folders/{folder_id}/favorites/{favorite_id}", headers=mine
        ).status_code
        == 204
    )
    assert api_client.delete(f"/api/v1/folders/{folder_id}", headers=mine).status_code == 204
    assert folder_id not in [
        f["id"] for f in api_client.get("/api/v1/folders", headers=mine).json()["data"]
    ]
