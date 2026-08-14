"""Generador documental (specs/doc-generator.md)."""

import pytest
from sqlalchemy import text

from app.core.db import session_factory
from tests.conftest import login_headers

pytestmark = pytest.mark.anyio


async def test_docgen_flow(api_client, make_user, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    owner = await make_user("employee")
    other = await make_user("employee")
    mine = login_headers(api_client, owner.email)

    created = api_client.post("/api/v1/doc-projects", json={"name": "Projecte prova"}, headers=mine)
    assert created.status_code == 201, created.text
    pid = created.json()["id"]

    # Propietat: l'altre usuari rep 404.
    assert (
        api_client.get(
            f"/api/v1/doc-projects/{pid}", headers=login_headers(api_client, other.email)
        ).status_code
        == 404
    )

    detail = api_client.get(f"/api/v1/doc-projects/{pid}", headers=mine).json()
    assert set(detail["documents"]) == {"PPA", "PPT", "REPORT"}

    # Referència: document indexat fals.
    async with session_factory() as session:
        cid = (
            await session.execute(
                text(
                    "INSERT INTO contracts (file_code, status, lot) "
                    "VALUES ('DOC/2026', 'Formalitzat', '') RETURNING id"
                )
            )
        ).scalar_one()
        did = (
            await session.execute(
                text(
                    "INSERT INTO phase_documents (contract_id, phase, title, doc_type, "
                    "storage_key, indexed_at) VALUES (:c, 'licitacio', 'PPT model', 'PPT', "
                    "'k', now()) RETURNING id"
                ),
                {"c": cid},
            )
        ).scalar_one()
        await session.execute(
            text(
                "INSERT INTO rag_chunks (document_id, contract_id, chunk_index, content, "
                "embedding) VALUES (:d, :c, 0, 'Contingut del plec de neteja model', "
                "CAST('[0.1,0.2,0.3,0.4]' AS vector))"
            ),
            {"d": did, "c": cid},
        )
        await session.commit()

    refs = api_client.put(
        f"/api/v1/doc-projects/{pid}/references", json={"document_ids": [did]}, headers=mine
    )
    assert refs.status_code == 200
    assert refs.json()["references"][0]["file_code"] == "DOC/2026"

    # Cercador de referències.
    found = api_client.get("/api/v1/doc-references", params={"q": "DOC/2026"}, headers=mine)
    assert any(r["id"] == did for r in found.json()["data"])

    # Índex sense perfil d'IA actiu → plantilla de fallback (mai error).
    async with session_factory() as session:
        enabled_ids = list(
            (
                await session.execute(
                    text("SELECT id FROM ai_provider_profiles WHERE enabled")
                )
            ).scalars()
        )
        await session.execute(text("UPDATE ai_provider_profiles SET enabled = false"))
        await session.commit()
    try:
        index = api_client.post(
            f"/api/v1/doc-projects/{pid}/documents/PPT/actions/generate-index", headers=mine
        )
        assert index.status_code == 200, index.text
        assert len(index.json()["sections"]) >= 5
    finally:
        async with session_factory() as session:
            if enabled_ids:
                await session.execute(
                    text("UPDATE ai_provider_profiles SET enabled = true WHERE id = ANY(:i)"),
                    {"i": enabled_ids},
                )
                await session.commit()

    # Edició manual de seccions.
    saved = api_client.patch(
        f"/api/v1/doc-projects/{pid}/documents/PPT",
        json={
            "sections": [
                {"title": "Objecte", "instructions": "", "content_md": "Text **fort**",
                 "sources": []}
            ]
        },
        headers=mine,
    )
    assert saved.status_code == 200

    # Export DOCX vàlid (magic PK zip).
    export = api_client.get(f"/api/v1/doc-projects/{pid}/documents/PPT/export.docx", headers=mine)
    assert export.status_code == 200
    assert export.content[:2] == b"PK"
    assert "wordprocessingml" in export.headers["content-type"]

    assert api_client.delete(f"/api/v1/doc-projects/{pid}", headers=mine).status_code == 204
