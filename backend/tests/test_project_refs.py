"""Referències externes de projecte (specs/docgen-external-refs.md)."""

import httpx
import pytest
from sqlalchemy import text

from app.ai import project_refs, providers, rag
from app.core.db import session_factory
from tests.conftest import login_headers

pytestmark = pytest.mark.anyio


def _embedding_transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json

        payload = _json.loads(request.read())
        data = [{"embedding": [0.5, 0.1, 0.2, 0.3]} for _ in payload["input"]]
        return httpx.Response(200, json={"data": data, "usage": {}})

    return httpx.MockTransport(handler)


async def _enable_fake_embeddings() -> None:
    async with session_factory() as session:
        await session.execute(
            text(
                "INSERT INTO ai_provider_profiles "
                "(name, protocol, base_url, default_model, enabled) "
                "VALUES ('refs-fake', 'openai_compatible', 'http://refs.fake/v1', 'emb', true) "
                "ON CONFLICT (name) DO UPDATE SET enabled = true"
            )
        )
        await session.commit()


async def test_external_ref_flow_and_isolation(
    api_client, make_user, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    owner = await make_user("employee")
    other = await make_user("employee")
    mine = login_headers(api_client, owner.email)
    await _enable_fake_embeddings()
    monkeypatch.setattr(providers, "_transport", _embedding_transport())

    pid = api_client.post("/api/v1/doc-projects", json={"name": "Refs ext"}, headers=mine).json()[
        "id"
    ]

    # Alta: crea el registre pendent i encua el job.
    added = api_client.post(
        f"/api/v1/doc-projects/{pid}/external-references",
        json={
            "title": "PPT d'un altre ens",
            "source_url": "https://contractaciopublica.cat/portal-api/descarrega-document/1/A",
            "file_code": "EXT/2026",
        },
        headers=mine,
    )
    assert added.status_code == 202, added.text
    ref_id = added.json()["id"]

    # Propietat: un altre usuari no pot afegir-ne al meu projecte.
    assert (
        api_client.post(
            f"/api/v1/doc-projects/{pid}/external-references",
            json={"title": "x", "source_url": "https://contractaciopublica.cat/x/y"},
            headers=login_headers(api_client, other.email),
        ).status_code
        == 404
    )

    # Simula la indexació del job sense xarxa: injecta descàrrega i extracció.
    class FakeClient:
        async def __aenter__(self):  # type: ignore[no-untyped-def]
            return self

        async def __aexit__(self, *args):  # type: ignore[no-untyped-def]
            return None

        async def download_document(self, url: str):  # type: ignore[no-untyped-def]
            return b"pdf-fals", "application/pdf"

    class FakeConnector:
        def client(self):  # type: ignore[no-untyped-def]
            return FakeClient()

    from app.integrations.pscp.connector import PscpConnector

    fake = FakeConnector()
    fake.__class__ = type("FakePscp", (PscpConnector,), {"client": FakeConnector.client})

    async def fake_get_connector(session, slug):  # type: ignore[no-untyped-def]
        return fake

    monkeypatch.setattr(project_refs.hub, "get_connector", fake_get_connector)
    monkeypatch.setattr(
        project_refs.rag,
        "extract_text",
        lambda content: "Plec extern de vigilància i seguretat d'edificis. " * 30,
    )

    class DummyStorage:
        async def put(self, key, content, content_type):  # type: ignore[no-untyped-def]
            return None

    monkeypatch.setattr(project_refs, "get_storage", lambda: DummyStorage())

    class Ctx:
        payload = {"project_document_id": ref_id}

        async def set_progress(self, *a, **k):  # type: ignore[no-untyped-def]
            return None

    result = await project_refs.index_external(Ctx())
    assert result["status"] == "indexed" and result["chunks"] >= 1

    # Cerca d'àmbit de projecte: troba el contingut.
    async with session_factory() as session:
        found = await project_refs.search_project_chunks(session, pid, "vigilància seguretat")
        assert found and found[0]["file_code"] == "EXT/2026"
        assert found[0]["origin"] == "extern"

        # AÏLLAMENT: el RAG general NO veu els fragments del projecte.
        general = await rag.search(session, "vigilància seguretat", limit=10)
        assert all("vigilància i seguretat d'edificis" not in r["content"] for r in general)

    # El detall del projecte mostra la referència indexada; esborrar en cascada.
    detail = api_client.get(f"/api/v1/doc-projects/{pid}", headers=mine).json()
    ext = detail["external_references"][0]
    assert ext["status"] == "indexed" and ext["chunks_count"] >= 1

    api_client.delete(f"/api/v1/doc-projects/{pid}", headers=mine)
    async with session_factory() as session:
        remaining = (
            await session.execute(
                text("SELECT count(*) FROM project_chunks WHERE project_id = :p"), {"p": pid}
            )
        ).scalar_one()
        assert remaining == 0
        await session.execute(text("DELETE FROM ai_provider_profiles WHERE name = 'refs-fake'"))
        await session.commit()


async def test_upload_local_pdf(api_client, make_user, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    """Pujada d'un PDF propi: validacions, storage directe i indexació sense
    descàrrega (specs/docgen-external-refs.md, ampliació 2026-08-17)."""
    owner = await make_user("employee")
    mine = login_headers(api_client, owner.email)
    await _enable_fake_embeddings()
    monkeypatch.setattr(providers, "_transport", _embedding_transport())

    pid = api_client.post("/api/v1/doc-projects", json={"name": "Pujades"}, headers=mine).json()[
        "id"
    ]

    stored: dict[str, bytes] = {}

    class DummyStorage:
        async def put(self, key, content, content_type):  # type: ignore[no-untyped-def]
            stored[key] = content

        async def get(self, key):  # type: ignore[no-untyped-def]
            return stored[key]

    import app.core.storage as storage_module
    import app.modules.docgen.router as docgen_router  # noqa: F401

    monkeypatch.setattr(storage_module, "get_storage", lambda: DummyStorage())
    monkeypatch.setattr(project_refs, "get_storage", lambda: DummyStorage())

    # Validacions: extensió, contingut buit i capçalera.
    assert (
        api_client.post(
            f"/api/v1/doc-projects/{pid}/external-references/upload",
            files={"file": ("nota.txt", b"hola", "text/plain")},
            headers=mine,
        ).status_code
        == 422
    )
    assert (
        api_client.post(
            f"/api/v1/doc-projects/{pid}/external-references/upload",
            files={"file": ("plec.pdf", b"aixo no es un pdf", "application/pdf")},
            headers=mine,
        ).status_code
        == 422
    )

    uploaded = api_client.post(
        f"/api/v1/doc-projects/{pid}/external-references/upload",
        files={"file": ("plec propi.pdf", b"%PDF-1.4 contingut", "application/pdf")},
        headers=mine,
    )
    assert uploaded.status_code == 202, uploaded.text
    ref_id = uploaded.json()["id"]
    assert stored  # el fitxer és a l'storage abans d'indexar

    async with session_factory() as session:
        row = (
            await session.execute(
                text("SELECT title, source_url, storage_key FROM project_documents WHERE id = :i"),
                {"i": ref_id},
            )
        ).first()
    assert row.source_url is None and row.storage_key.startswith(f"projects/{pid}/")
    assert row.title == "plec propi.pdf"

    # El job indexa des de l'storage sense tocar cap connector.
    async def no_connector(session, slug):  # type: ignore[no-untyped-def]
        raise AssertionError("no s'ha de descarregar res per a una pujada local")

    monkeypatch.setattr(project_refs.hub, "get_connector", no_connector)
    monkeypatch.setattr(
        project_refs.rag,
        "extract_text",
        lambda content: "Memòria tècnica pròpia del servei municipal. " * 30,
    )

    class Ctx:
        payload = {"project_document_id": ref_id}

        async def set_progress(self, *a, **k):  # type: ignore[no-untyped-def]
            return None

    result = await project_refs.index_external(Ctx())
    assert result["status"] == "indexed" and result["chunks"] >= 1

    async with session_factory() as session:
        found = await project_refs.search_project_chunks(session, pid, "memòria tècnica")
    assert found and found[0]["origin"] == "extern"
