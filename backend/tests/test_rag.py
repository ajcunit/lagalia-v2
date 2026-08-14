"""Servei RAG (specs/rag-service.md): chunker, ingesta i cerca amb dobles."""

import httpx
import pytest
from sqlalchemy import text

from app.ai import providers, rag
from app.core.db import session_factory
from tests.conftest import login_headers

pytestmark = pytest.mark.anyio


def test_chunker_respects_paragraphs_and_overlap() -> None:
    paragraph = ("Frase de prova amb contingut suficient per superar el filtre. " * 20).strip()
    value = "\n\n".join([paragraph, paragraph, paragraph])
    chunks = rag.chunk_text(value)
    assert len(chunks) >= 2
    assert all(len(c) <= rag.CHUNK_SIZE + 100 for c in chunks)
    # Solapament: el segon chunk comença dins del final del primer.
    assert chunks[1][:80] in value


def test_chunker_skips_tiny_fragments() -> None:
    assert rag.chunk_text("curt") == []


async def _fake_profile() -> int:
    async with session_factory() as session:
        pid = (
            await session.execute(
                text(
                    "INSERT INTO ai_provider_profiles "
                    "(name, protocol, base_url, default_model, enabled) "
                    "VALUES ('rag-fake', 'openai_compatible', 'http://rag.fake/v1', 'emb', true) "
                    "ON CONFLICT (name) DO UPDATE SET enabled = true RETURNING id"
                )
            )
        ).scalar_one()
        await session.commit()
    return pid


def _embedding_transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json

        payload = _json.loads(request.read())
        texts = payload["input"]
        # Vector determinista de dimensió 4 segons el contingut.
        data = [
            {"embedding": [len(t) % 7 / 10, t.count("neteja") / 2, 0.1, 0.2]}
            for t in texts
        ]
        return httpx.Response(200, json={"data": data, "usage": {"prompt_tokens": 1}})

    return httpx.MockTransport(handler)


async def test_index_and_search(monkeypatch: pytest.MonkeyPatch, api_client, make_user) -> None:  # type: ignore[no-untyped-def]
    await _fake_profile()
    monkeypatch.setattr(providers, "_transport", _embedding_transport())

    # Document fals amb storage en memòria.
    class FakeStorage:
        async def get(self, key: str) -> bytes:
            raise AssertionError("no s'ha de cridar en aquest test")

    async with session_factory() as session:
        contract_id = (
            await session.execute(
                text(
                    "INSERT INTO contracts (file_code, status, lot) "
                    "VALUES ('RAG/2026', 'Formalitzat', '') RETURNING id"
                )
            )
        ).scalar_one()
        doc_id = (
            await session.execute(
                text(
                    "INSERT INTO phase_documents (contract_id, phase, title, doc_type, "
                    "storage_key) VALUES (:c, 'licitacio', 'PPT neteja', 'PPT', 'k') RETURNING id"
                ),
                {"c": contract_id},
            )
        ).scalar_one()
        await session.commit()

    # Injecta el text directament (sense PDF): monkeypatch d'extract i storage.
    monkeypatch.setattr(rag, "extract_text", lambda content: (
        "Plec de prescripcions del servei de neteja d'edificis municipals. " * 40
    ))

    class DummyStorage:
        async def get(self, key: str) -> bytes:
            return b"pdf-fals"

    monkeypatch.setattr(rag, "get_storage", lambda: DummyStorage())

    async with session_factory() as session:
        n = await rag.index_document(session, doc_id)
        await session.commit()
    assert n >= 1

    async with session_factory() as session:
        results = await rag.search(session, "servei de neteja", limit=5)
    assert results and results[0]["file_code"] == "RAG/2026"
    assert "neteja" in results[0]["content"]

    # API de cerca amb sessió.
    user = await make_user("employee")
    response = api_client.post(
        "/api/v1/rag/search",
        json={"query": "servei de neteja"},
        headers=login_headers(api_client, user.email),
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]

    # Neteja del perfil per no contaminar altres tests.
    async with session_factory() as session:
        await session.execute(text("DELETE FROM ai_provider_profiles WHERE name = 'rag-fake'"))
        await session.commit()
