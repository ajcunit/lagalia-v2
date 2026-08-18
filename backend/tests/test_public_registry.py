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


def test_soql_aggregates_validated() -> None:
    from app.integrations.socrata.query import SoqlQuery, SoqlValidationError

    q = (
        SoqlQuery("ybgg-dgi6")
        .where_eq("identificacio_adjudicatari", "B123")
        .select("nom_organ")
        .select_count_distinct("codi_expedient", "expedients")
        .select_aggregate("sum", "import_adjudicacio_sense", "import_total")
        .group_by("nom_organ")
        .order_by("import_total", descending=True)
    )
    params = q.params()
    assert params["$group"] == "nom_organ"
    assert "count(distinct codi_expedient) AS expedients" in params["$select"]

    import pytest as _pytest

    with _pytest.raises(SoqlValidationError):
        SoqlQuery("ybgg-dgi6").select_aggregate("delete", "x", "y")
    with _pytest.raises(SoqlValidationError):
        SoqlQuery("ybgg-dgi6").select_aggregate("sum", "x; drop", "y")
    with _pytest.raises(SoqlValidationError):
        SoqlQuery("ybgg-dgi6").select_aggregate("avg", None, "y")


async def test_contractor_analysis_endpoint(
    api_client, make_user, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    from tests.conftest import login_headers

    user = await make_user("employee")
    headers = login_headers(api_client, user.email)

    # Connector simulat: cada consulta retorna files agregades canòniques.
    calls: list[dict] = []

    class FakeClient:
        async def __aenter__(self):  # type: ignore[no-untyped-def]
            return self

        async def __aexit__(self, *args):  # type: ignore[no-untyped-def]
            return None

        async def fetch_page(self, query):  # type: ignore[no-untyped-def]
            params = query.params()
            calls.append(params)
            select = params["$select"]
            if "$group" not in params:
                if "expedients_formalitzats" in select:
                    return [{"expedients_formalitzats": "8", "import_total": "100000",
                             "import_mitja": "12500"}]
                return [{"expedients": "12", "organs": "3",
                         "primera": "2020-01-01T00:00:00.000",
                         "darrera": "2026-06-01T00:00:00.000"}]
            if "nom_organ" in select and "import_total" in select:
                return [{"nom_organ": "Ajuntament de Cunit",
                         "expedients_formalitzats": "6",
                         "import_total": "60000", "import_mitja": "10000"}]
            if "nom_organ" in select:
                return [
                    {"nom_organ": "Ajuntament de Cunit", "expedients": "9"},
                    {"nom_organ": "Ajuntament de Calafell", "expedients": "3"},
                ]
            if "import_total" in select:
                return [{"tipus_contracte": "Serveis", "expedients_formalitzats": "8",
                         "import_total": "100000"}]
            return [{"tipus_contracte": "Serveis", "expedients": "12"}]

    class FakeConnector:
        config = {"dataset_contracts": "ybgg-dgi6", "base_url": "https://x"}

        def client(self):  # type: ignore[no-untyped-def]
            return FakeClient()

    from app.integrations.socrata.connector import SocrataConnector
    from app.modules.public_registry import router as pr_router

    fake = FakeConnector()
    fake.__class__ = type(
        "FakeSocrata", (SocrataConnector,), {"client": FakeConnector.client}
    )
    fake.config = FakeConnector.config

    async def fake_get_connector(session, slug):  # type: ignore[no-untyped-def]
        return fake

    monkeypatch.setattr(pr_router.hub, "get_connector", fake_get_connector)

    response = api_client.get(
        "/api/v1/public-registry/contractor-analysis",
        params={"tax_id": "B59357707"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["totals"]["expedients"] == "12"
    assert payload["totals"]["import_total"] == "100000"
    # Fusió coherent: publicats (totes les fases) + formalitzats amb imports.
    cunit = payload["by_organ"][0]
    assert cunit["nom_organ"] == "Ajuntament de Cunit"
    assert cunit["expedients"] == "9"
    assert cunit["expedients_formalitzats"] == "6"
    calafell = payload["by_organ"][1]
    assert calafell["expedients"] == "3" and "import_total" not in calafell
    assert payload["by_type"][0]["tipus_contracte"] == "Serveis"
    assert payload["by_type"][0]["expedients"] == "12"
    assert len(calls) == 6
    # Tot filtrat pel NIF, mai SoQL cru de l'usuari.
    assert all("identificacio_adjudicatari = 'B59357707'" in c["$where"] for c in calls)

    # tax_id massa curt → 422.
    assert (
        api_client.get(
            "/api/v1/public-registry/contractor-analysis",
            params={"tax_id": "AB"},
            headers=headers,
        ).status_code
        == 422
    )
