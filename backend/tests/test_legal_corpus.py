"""Corpus normatiu BOE i revisió legal (specs/legal-corpus.md)."""

import pytest
from sqlalchemy import text

from app.ai import legal_corpus
from app.core.db import session_factory
from app.integrations.boe.connector import parse_articles
from tests.conftest import login_headers

pytestmark = pytest.mark.anyio

SAMPLE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<documento fecha_actualizacion="20260812122601">
  <metadatos>
    <identificador>BOE-A-TEST-1</identificador>
    <titulo>Ley de prova</titulo>
    <rango>Ley</rango>
    <fecha_publicacion>20171109</fecha_publicacion>
  </metadatos>
  <texto>
    <p>Artículo 1. Objeto.</p>
    <p>Artículo 2. Ambito.</p>
    <p>Artículo 1. Objeto.</p>
    <p>El cos real del primer article, prou llarg per superar el filtre de vuitanta
    caracters que descarta les entrades de l'index sense contingut.</p>
    <p>Artículo 2. Ambito.</p>
    <p>El cos del segon article, tambe amb prou text per no ser descartat pel filtre
    de longitud minima que aplica el parser del connector.</p>
  </texto>
</documento>""".encode()


def test_parse_articles_keeps_body_not_index() -> None:
    meta, articles = parse_articles(SAMPLE_XML)
    assert meta["titulo"] == "Ley de prova"
    assert meta["fecha_actualizacion"] == "20260812122601"
    labels = {a["label"] for a in articles}
    assert labels == {"Artículo 1", "Artículo 2"}
    first = next(a for a in articles if a["label"] == "Artículo 1")
    assert "cos real del primer article" in first["content"]


def test_rule_article_labels_seed_from_engine() -> None:
    labels = legal_corpus.rule_article_labels()
    assert "Artículo 118" in labels  # llindars del menor
    assert "Artículo 29" in labels  # durada


async def test_legal_norms_api(api_client, make_user) -> None:  # type: ignore[no-untyped-def]
    admin_user = await make_user("admin")
    employee = await make_user("employee")
    admin = login_headers(api_client, admin_user.email)

    assert (
        api_client.get(
            "/api/v1/legal/norms", headers=login_headers(api_client, employee.email)
        ).status_code
        == 403
    )

    async with session_factory() as session:
        await session.execute(
            text(
                "INSERT INTO legal_norms (boe_id, title, rank, consolidated_version, "
                "articles_count) VALUES ('BOE-A-TEST-2', 'Norma de prova', 'Ley', '2026', 3) "
                "ON CONFLICT (boe_id) DO NOTHING"
            )
        )
        await session.commit()

    listing = api_client.get("/api/v1/legal/norms", headers=admin)
    assert listing.status_code == 200
    assert any(n["boe_id"] == "BOE-A-TEST-2" for n in listing.json()["data"])

    async with session_factory() as session:
        await session.execute(text("DELETE FROM legal_norms WHERE boe_id = 'BOE-A-TEST-2'"))
        await session.commit()


async def test_subscribe_and_unsubscribe_norm(api_client, make_user) -> None:  # type: ignore[no-untyped-def]
    """Alta i baixa de normes des de la pantalla (specs/legal-corpus.md)."""
    from sqlalchemy import text as sql_text

    from app.core.db import session_factory
    from tests.conftest import login_headers

    admin_user = await make_user("admin")
    employee = await make_user("employee")
    admin = login_headers(api_client, admin_user.email)

    # Permisos i validació.
    assert (
        api_client.post(
            "/api/v1/legal/norms",
            json={"boe_id": "BOE-A-2011-17887"},
            headers=login_headers(api_client, employee.email),
        ).status_code
        == 403
    )
    assert (
        api_client.post(
            "/api/v1/legal/norms", json={"boe_id": "no-es-un-id"}, headers=admin
        ).status_code
        == 422
    )

    # Alta: entra a la config del connector i s'encua la indexació.
    created = api_client.post(
        "/api/v1/legal/norms", json={"boe_id": "BOE-A-2011-17887"}, headers=admin
    )
    assert created.status_code == 202, created.text
    assert created.json()["job_id"]

    # Duplicat → 409.
    assert (
        api_client.post(
            "/api/v1/legal/norms", json={"boe_id": "BOE-A-2011-17887"}, headers=admin
        ).status_code
        == 409
    )

    async with session_factory() as session:
        config = (
            await session.execute(sql_text("SELECT config FROM connectors WHERE slug = 'boe'"))
        ).scalar_one()
    assert "BOE-A-2011-17887" in (config or {}).get("norm_ids", [])

    # Simula que la norma s'ha indexat per comprovar l'esborrat en la baixa.
    async with session_factory() as session:
        norm_id = (
            await session.execute(
                sql_text(
                    "INSERT INTO legal_norms (boe_id, title) "
                    "VALUES ('BOE-A-2011-17887', 'TRLCSP (prova)') RETURNING id"
                )
            )
        ).scalar_one()
        await session.execute(
            sql_text(
                "INSERT INTO legal_chunks (norm_id, article_label, chunk_index, content) "
                "VALUES (:n, 'Artículo 1', 0, 'text de prova')"
            ),
            {"n": norm_id},
        )
        await session.commit()

    # Baixa: fora de la config i índex esborrat (chunks per CASCADE).
    assert (
        api_client.delete("/api/v1/legal/norms/BOE-A-2011-17887", headers=admin).status_code == 204
    )
    async with session_factory() as session:
        config = (
            await session.execute(sql_text("SELECT config FROM connectors WHERE slug = 'boe'"))
        ).scalar_one()
        remaining = (
            await session.execute(
                sql_text("SELECT count(*) FROM legal_norms WHERE boe_id = 'BOE-A-2011-17887'")
            )
        ).scalar_one()
        await session.execute(sql_text("DELETE FROM jobs WHERE type = 'sync.boe_norms'"))
        await session.commit()
    assert "BOE-A-2011-17887" not in (config or {}).get("norm_ids", [])
    assert remaining == 0

    # Norma no subscrita → 404.
    assert (
        api_client.delete("/api/v1/legal/norms/BOE-A-1999-99999", headers=admin).status_code == 404
    )
