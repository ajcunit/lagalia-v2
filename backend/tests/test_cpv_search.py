"""Cercador CPV (specs/cpv-search.md)."""

import pytest
from sqlalchemy import text

from app.core.db import session_factory
from tests.conftest import login_headers

pytestmark = pytest.mark.anyio


async def test_cpv_search(api_client, make_user) -> None:  # type: ignore[no-untyped-def]
    async with session_factory() as session:
        await session.execute(
            text(
                "INSERT INTO cpv_codes (code, description, level, parent_code) VALUES "
                "('03000000-1', 'Productes agraris', 'Division', NULL), "
                "('03100000-2', 'Agricultura i horticultura', 'Group', '03000000-1') "
                "ON CONFLICT (code) DO NOTHING"
            )
        )
        await session.commit()

    user = await make_user("employee")
    headers = login_headers(api_client, user.email)

    assert api_client.get("/api/v1/cpv").status_code == 401

    roots = api_client.get("/api/v1/cpv", headers=headers).json()["data"]
    root = next(r for r in roots if r["code"] == "03000000-1")
    assert root["has_children"] is True

    kids = api_client.get("/api/v1/cpv", params={"parent": "03000000-1"}, headers=headers)
    assert [k["code"] for k in kids.json()["data"]] == ["03100000-2"]
    assert kids.json()["data"][0]["has_children"] is False

    by_text = api_client.get("/api/v1/cpv", params={"query": "horticult"}, headers=headers)
    assert any(r["code"] == "03100000-2" for r in by_text.json()["data"])
    by_code = api_client.get("/api/v1/cpv", params={"query": "0310"}, headers=headers)
    assert any(r["code"] == "03100000-2" for r in by_code.json()["data"])
