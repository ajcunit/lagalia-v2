"""Connector pscp: extracció (fixtures reals) i enriquiment e2e simulat."""

import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.db import session_factory
from app.integrations import hub
from app.integrations.base import ConnectorError
from app.integrations.pscp import extract
from app.integrations.pscp.connector import PscpClient, PscpConnector
from app.integrations.pscp.enrich import enrich_contract
from app.jobs.registry import JobContext

FIXTURES = Path(__file__).parent / "fixtures"
LICITACIO = json.loads((FIXTURES / "pscp_licitacio.json").read_text(encoding="utf-8"))
ADJUDICACIO = json.loads((FIXTURES / "pscp_adjudicacio.json").read_text(encoding="utf-8"))
BASE = "https://contractaciopublica.cat"


# ─────────────────────────── extracció (unitats) ───────────────────────────


def test_ml_fallback_ca_es_en() -> None:
    assert extract.ml({"ca": "Català", "es": "Castellà"}) == "Català"
    assert extract.ml({"ca": "", "es": "Castellano"}) == "Castellano"
    assert extract.ml({"en": "English only"}) == "English only"
    assert extract.ml({"oc": "Occità"}) is None
    assert extract.ml("text pla") == "text pla"
    assert extract.ml(None) is None


def test_scalars_from_real_licitacio() -> None:
    scalars = extract.extract_scalars("licitacio", LICITACIO)

    assert scalars["is_harmonized"] is False
    assert scalars["allows_extensions"] is True
    assert "allows_modifications" in scalars


def test_scalars_from_real_adjudicacio() -> None:
    scalars = extract.extract_scalars("adjudicacio", ADJUDICACIO)

    assert scalars["winner_name"] == "TALLER D'ART, CULTURA I CREACIÓ"
    assert scalars["winner_tax_id"] == "G65643405"
    assert str(scalars["award_amount"]) == "87933.3"


def test_criteria_from_real_adjudicacio() -> None:
    criteria = extract.collect_criteria(ADJUDICACIO)

    assert criteria
    first = criteria[0]
    assert first["name"] == "Preu"
    assert str(first["weight"]) == "50"
    assert first["position"] == 1
    assert "desglossament" in first["breakdown"]


def test_documents_from_real_fixture() -> None:
    documents = extract.collect_documents(LICITACIO, BASE)

    assert len(documents) >= 2
    first = documents[0]
    assert first["source_doc_id"].isdigit()
    assert first["download_url"].startswith(f"{BASE}/portal-api/descarrega-document/")
    assert first["title"]


def test_committee_never_from_contact_persons() -> None:
    # L'òrgan té personesContacte amb nom/cognom/càrrec: NO són mesa.
    members = extract.collect_committee(LICITACIO)
    assert members == []

    # Esquema real: publicacio.dadesPublicacio.membresMesa amb `cognoms`.
    with_mesa = {
        "publicacio": {
            "dadesPublicacio": {
                "membresMesa": [
                    {
                        "nom": "Anna",
                        "cognoms": "Puig Serra",
                        "carrec": {"id": 487, "ca": "Presidenta"},
                    }
                ]
            }
        }
    }
    members = extract.collect_committee(with_mesa)
    assert members == [{"first_name": "Anna", "last_name": "Puig Serra", "role": "Presidenta"}]


# ─────────────────────────── enriquiment e2e ───────────────────────────


class FakePscp:
    def __init__(self) -> None:
        self.phases: dict[str, dict[str, Any]] = {}
        self.document_body = b"PDF-fals-per-a-tests"

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.startswith("/portal-api/descarrega-document/"):
            return httpx.Response(
                200, content=self.document_body, headers={"content-type": "application/pdf"}
            )
        for name, payload in self.phases.items():
            if name in path:
                return httpx.Response(200, json=payload)
        return httpx.Response(404)


@pytest.fixture
async def pscp_world(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> AsyncIterator[dict[str, Any]]:
    fake = FakePscp()
    fake.phases = {"licitacio": LICITACIO, "adjudicacio": ADJUDICACIO}

    def fake_client(self: PscpConnector) -> PscpClient:
        return PscpClient(
            BASE,
            min_interval_seconds=0,
            max_document_bytes=1024 * 1024,
            transport=httpx.MockTransport(fake.handler),
        )

    monkeypatch.setattr(PscpConnector, "client", fake_client)
    monkeypatch.setattr(settings, "storage_backend", "filesystem")
    monkeypatch.setattr(settings, "storage_local_path", str(tmp_path))

    tag = uuid4().hex[:8]
    async with session_factory() as session:
        record = await hub.ensure_registered(session, "pscp")
        was_enabled = record.enabled
        record.enabled = True
        contract_id = (
            await session.execute(
                text(
                    "INSERT INTO contracts (file_code, status, lot, subject, phase_urls) "
                    "VALUES (:f, 'Adjudicat', '', 'Servei enriquible', :urls) RETURNING id"
                ),
                {
                    "f": f"ENR-{tag}/1",
                    "urls": json.dumps(
                        {
                            "licitacio": f"{BASE}/documents/json-xifrat/licitacio/x",
                            "adjudicacio": f"{BASE}/documents/json-xifrat/adjudicacio/x",
                        }
                    ),
                },
            )
        ).scalar_one()
        await session.commit()

    yield {"tag": tag, "contract_id": contract_id, "fake": fake, "storage": tmp_path}

    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.execute(
            text("DELETE FROM contracts WHERE file_code LIKE :p"), {"p": f"ENR-{tag}%"}
        )
        if not was_enabled:
            await conn.execute(text("UPDATE connectors SET enabled = false WHERE slug = 'pscp'"))
    await engine.dispose()


async def _run_enrich(payload: dict[str, Any]) -> dict[str, Any]:
    async def _noop(_pct: int, _msg: str | None = None) -> None:
        return None

    result = await enrich_contract(JobContext(job_id=uuid4(), payload=payload, set_progress=_noop))
    assert result is not None
    return result


async def test_enrich_contract_end_to_end(pscp_world: dict[str, Any]) -> None:
    contract_id = pscp_world["contract_id"]

    result = await _run_enrich({"contract_id": contract_id})
    assert result["phases"] == 2
    assert result["documents"] >= 2
    assert result["stored"] == result["documents"]

    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    async with engine.connect() as conn:
        row = (
            (
                await conn.execute(
                    text(
                        "SELECT enriched_at, is_harmonized, allows_extensions, enrichment "
                        "FROM contracts WHERE id = :id"
                    ),
                    {"id": contract_id},
                )
            )
            .mappings()
            .one()
        )
        documents = (
            await conn.execute(
                text(
                    "SELECT title, storage_key, size, download_url FROM phase_documents "
                    "WHERE contract_id = :id"
                ),
                {"id": contract_id},
            )
        ).all()
    await engine.dispose()

    assert row["enriched_at"] is not None
    assert row["is_harmonized"] is False
    assert row["allows_extensions"] is True
    assert "licitacio" in row["enrichment"]
    assert documents
    for document in documents:
        assert document.storage_key
        assert document.size == len(pscp_world["fake"].document_body)
        # El fitxer és realment a l'emmagatzematge local.
        assert (pscp_world["storage"] / document.storage_key).exists()

    # Idempotent: sense force fa skip; amb force refresca.
    assert (await _run_enrich({"contract_id": contract_id}))["skipped"] is True
    assert "phases" in await _run_enrich({"contract_id": contract_id, "force": True})


async def test_stale_phase_is_skipped_but_rest_enriches(pscp_world: dict[str, Any]) -> None:
    # La fase d'adjudicació «caduca» (404 a la font): s'enriqueix amb la resta.
    pscp_world["fake"].phases.pop("adjudicacio")

    result = await _run_enrich({"contract_id": pscp_world["contract_id"]})
    assert result["phases"] == 1
    assert result["skipped_phases"] == ["adjudicacio"]

    # Si cap fase respon, el job falla amb error explícit.
    pscp_world["fake"].phases.clear()
    with pytest.raises(ConnectorError, match="cap fase disponible"):
        await _run_enrich({"contract_id": pscp_world["contract_id"], "force": True})


async def test_document_host_outside_domain_is_rejected() -> None:
    client = PscpClient(BASE, min_interval_seconds=0, max_document_bytes=1024)

    with pytest.raises(ConnectorError, match="fora del domini"):
        await client.download_document("https://malici.os/doc/1/x")
    await client.__aexit__(None, None, None)


def test_doc_type_not_polluted_by_language_keys() -> None:
    """El doc_type és el grup real, no la clau d'idioma (fix 2026-08-18)."""
    from app.integrations.pscp import extract

    payload = {
        "publicacio": {
            "plecAdministratiu": {
                "ca": [{"id": 1, "titol": "PCA.pdf", "hash": "A", "mida": "10"}]
            },
            "plecTecnic": {
                "ca": [{"id": 2, "titol": "PPT.pdf", "hash": "B", "mida": "20"}]
            },
        }
    }
    documents = extract.collect_documents(payload, "https://x")
    by_id = {d["source_doc_id"]: d["doc_type"] for d in documents}
    assert by_id == {"1": "plecAdministratiu", "2": "plecTecnic"}


async def test_indexable_phases_filter(api_client, make_user) -> None:  # type: ignore[no-untyped-def]
    """L'allowlist de fases limita quins documents es descarreguen; la resta
    queden com a enllaç (specs/rag-service.md)."""
    import json as _json

    from sqlalchemy import text as sql_text

    from app.core.db import session_factory
    from app.integrations.pscp.enrich import _indexable_phases
    from tests.conftest import login_headers

    async with session_factory() as session:
        assert await _indexable_phases(session) is None  # sense setting → totes
        await session.execute(
            sql_text(
                "INSERT INTO settings (key, value, is_secret) "
                "VALUES ('rag.indexable_phases', CAST(:v AS jsonb), false) "
                "ON CONFLICT (key) DO UPDATE SET value = CAST(:v AS jsonb)"
            ),
            {"v": _json.dumps(["licitacio", "adjudicacio"])},
        )
        await session.commit()
    async with session_factory() as session:
        allowed = await _indexable_phases(session)
    assert allowed == {"licitacio", "adjudicacio"}

    # L'endpoint de fases respon amb comptadors (admin).
    admin_user = await make_user("admin")
    admin = login_headers(api_client, admin_user.email)
    response = api_client.get("/api/v1/rag/phases", headers=admin)
    assert response.status_code == 200, response.text

    async with session_factory() as session:
        await session.execute(
            sql_text("DELETE FROM settings WHERE key = 'rag.indexable_phases'")
        )
        await session.commit()
