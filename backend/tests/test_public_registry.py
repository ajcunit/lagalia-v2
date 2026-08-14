"""SuperBuscador (specs/super-search.md): builder i proxys, sense xarxa."""

import pytest

from app.integrations.socrata.query import SoqlQuery, SoqlValidationError
from tests.conftest import login_headers

pytestmark = pytest.mark.anyio


def test_soql_full_text_and_contains() -> None:
    query = (
        SoqlQuery("ybgg-dgi6")
        .full_text("neteja d'escoles")
        .where_contains("nom_organ", "Ajuntament % de _ Cunit")
        .where_gte_number("pressupost_licitacio_amb", "1000.50")
        .where_lte_number("pressupost_licitacio_amb", 200000)
        .where_lte_timestamp("data_publicacio_anunci", "2026-01-31T23:59:59")
    )
    params = query.params()
    # $q viatja com a paràmetre, mai dins de $where.
    assert params["$q"] == "neteja d'escoles"
    assert "neteja" not in params["$where"]
    # Els comodins de l'usuari es neutralitzen; el literal va escapat i en majúscules.
    assert "AJUNTAMENT" in params["$where"]
    assert "%25" not in params["$where"]
    assert "upper(nom_organ) like" in params["$where"]
    assert params["$where"].count("%") == 2  # només els dos comodins nostres
    # Rangs tipats.
    assert "pressupost_licitacio_amb >= 1000.50" in params["$where"]
    assert "pressupost_licitacio_amb <= 200000" in params["$where"]
    assert "data_publicacio_anunci <= '2026-01-31T23:59:59'" in params["$where"]


def test_soql_contains_only_wildcards_is_noop() -> None:
    query = SoqlQuery("ybgg-dgi6").where_contains("nom_organ", "%_%")
    assert "$where" not in query.params()


def test_soql_lte_number_validates() -> None:
    with pytest.raises(SoqlValidationError):
        SoqlQuery("ybgg-dgi6").where_lte_number("camp", "no-numeric")


def test_soql_quotes_escaped_in_contains() -> None:
    params = SoqlQuery("ybgg-dgi6").where_contains("nom_organ", "l'hospitalet").params()
    # L'apòstrof queda doblat dins del literal: no pot tancar la cadena.
    assert "L''HOSPITALET" in params["$where"]


async def test_public_registry_api_guards(api_client, make_user) -> None:  # type: ignore[no-untyped-def]
    # Sense sessió → 401 (mai proxy anònim).
    assert api_client.get("/api/v1/public-registry/search").status_code == 401

    user = await make_user("employee")
    headers = login_headers(api_client, user.email)

    # BD efímera: el connector pscp neix desactivat; l'anti-SSRF es comprova
    # amb el connector actiu (si no, el 409 de desactivat arriba abans).
    from sqlalchemy import text as sql_text

    from app.core.db import session_factory
    from app.integrations import hub

    async with session_factory() as session:
        await hub.ensure_registered(session, "pscp")
        await session.execute(
            sql_text("UPDATE connectors SET enabled = true WHERE slug = 'pscp'")
        )
        await session.commit()

    # Fase amb URL fora del domini del connector pscp → 422 (anti-SSRF), sense xarxa.
    bad = api_client.get(
        "/api/v1/public-registry/phase",
        params={"url": "https://atacant.example.com/portal-api/fase.json"},
        headers=headers,
    )
    assert bad.status_code == 422, bad.text

    # Paràmetres invàlids → 422 del contracte.
    assert (
        api_client.get(
            "/api/v1/public-registry/search", params={"page_size": 500}, headers=headers
        ).status_code
        == 422
    )
