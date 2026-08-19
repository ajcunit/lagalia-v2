"""Centre d'ajuda integrat (specs/help-wiki.md)."""

import pytest
from fastapi.testclient import TestClient

from app.modules.help.articles import ARTICLES
from tests.conftest import MakeUser, login_headers

pytestmark = pytest.mark.anyio


def test_articles_are_wellformed() -> None:
    slugs = [a.slug for a in ARTICLES]
    assert len(slugs) == len(set(slugs))  # slugs únics
    assert all(a.body.strip() and a.title.strip() for a in ARTICLES)
    assert any(a.audience == "admin" for a in ARTICLES)
    assert any(a.audience == "all" for a in ARTICLES)


async def test_employee_sees_only_general_articles(
    api_client: TestClient, make_user: MakeUser
) -> None:
    employee = await make_user("employee")
    headers = login_headers(api_client, employee.email)

    listed = api_client.get("/api/v1/help", headers=headers)
    assert listed.status_code == 200
    audiences = {item["audience"] for item in listed.json()["data"]}
    assert audiences == {"all"}

    # Un article d'admin ni tan sols existeix per a ell.
    admin_slug = next(a.slug for a in ARTICLES if a.audience == "admin")
    hidden = api_client.get(f"/api/v1/help/{admin_slug}", headers=headers)
    assert hidden.status_code == 404

    general_slug = next(a.slug for a in ARTICLES if a.audience == "all")
    article = api_client.get(f"/api/v1/help/{general_slug}", headers=headers)
    assert article.status_code == 200
    assert article.json()["body"]


async def test_admin_sees_everything(api_client: TestClient, make_user: MakeUser) -> None:
    admin = await make_user("admin")
    headers = login_headers(api_client, admin.email)

    listed = api_client.get("/api/v1/help", headers=headers)
    assert listed.status_code == 200
    assert {item["audience"] for item in listed.json()["data"]} == {"all", "admin"}


async def test_chat_help_tool_serves_only_general_audience() -> None:
    from app.ai.analyst_tools import help_articles

    results = await help_articles(None, {"q": "sincronització nocturna programació"})  # type: ignore[arg-type]
    assert results  # troba articles rellevants
    admin_slugs = {a.slug for a in ARTICLES if a.audience == "admin"}
    assert all(r["slug"] not in admin_slugs for r in results)

    # Sense consulta: retorna una mostra del manual, mai articles d'admin.
    everything = await help_articles(None, {})  # type: ignore[arg-type]
    assert everything and all(r["slug"] not in admin_slugs for r in everything)
