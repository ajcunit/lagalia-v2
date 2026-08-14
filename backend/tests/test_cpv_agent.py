"""Agent CPV (specs/cpv-ai-suggest.md): pipeline i endpoints."""

import httpx
import pytest
from sqlalchemy import text

from app.ai import cpv_agent, providers
from app.core.db import session_factory
from tests.conftest import login_headers

pytestmark = pytest.mark.anyio


def test_pipeline_helpers() -> None:
    assert cpv_agent.clean_description("Contracte de servei de neteja") == "neteja"
    assert cpv_agent.detect_type("servei de manteniment de jardins") == "servei"
    assert cpv_agent.detect_type("obres de pavimentació") == "obra"
    assert cpv_agent.stem_ca("jardins") == "jardi"
    assert cpv_agent.strip_json('<think>bla</think>```json\n[{"a":1}]\n```') == '[{"a":1}]'


async def _seed_cpv() -> None:
    async with session_factory() as session:
        await session.execute(
            text(
                "INSERT INTO cpv_codes (code, description, level) VALUES "
                "('77310000-6', 'Serveis de plantació i manteniment de zones verdes', 'Class'), "
                "('77311000-3', 'Serveis de manteniment de jardins i parcs', 'Category') "
                "ON CONFLICT (code) DO NOTHING"
            )
        )
        await session.commit()


async def test_suggest_endpoint_llm_and_fallback(
    api_client, make_user, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    await _seed_cpv()
    user = await make_user("employee")
    headers = login_headers(api_client, user.email)

    # Sense cap perfil actiu → 409 clar.
    denied = api_client.post(
        "/api/v1/ai/cpv/suggest", json={"text": "servei de jardineria"}, headers=headers
    )
    assert denied.status_code == 409

    # Perfil fals actiu + transport fals: extract JSON + rank JSON.
    async with session_factory() as session:
        await session.execute(
            text(
                "INSERT INTO ai_provider_profiles "
                "(name, protocol, base_url, default_model, enabled) "
                "VALUES ('fake', 'openai_compatible', 'http://fake.test/v1', 'm', true)"
            )
        )
        await session.commit()

    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:  # extract
            content = '{"keywords": ["jardineria"], "divisions": ["77"], "codes": []}'
        else:  # rank
            content = (
                '[{"code": "77311000-3", "description": "x", "score": 0.9,'
                ' "justification": "manteniment de jardins"}]'
            )
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": content}}], "usage": {}},
        )

    monkeypatch.setattr(providers, "_transport", httpx.MockTransport(handler))
    response = api_client.post(
        "/api/v1/ai/cpv/suggest",
        json={"text": "Servei de manteniment de la jardineria municipal"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["source"] == "llm"
    assert body["suggestions"][0]["code"] == "77311000-3"

    # Feedback registrat.
    feedback = api_client.post(
        "/api/v1/ai/cpv/feedback",
        json={
            "query_text": "jardineria",
            "chosen_code": "77311000-3",
            "suggested": body["suggestions"],
        },
        headers=headers,
    )
    assert feedback.status_code == 201
    async with session_factory() as session:
        count = (
            await session.execute(
                text("SELECT count(*) FROM ai_cpv_feedback WHERE chosen_code = '77311000-3'")
            )
        ).scalar_one()
    assert count >= 1

    # Model que respon brossa → fallback lèxic, mai error.
    def bad_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "no sóc JSON"}}], "usage": {}}
        )

    monkeypatch.setattr(providers, "_transport", httpx.MockTransport(bad_handler))
    fallback = api_client.post(
        "/api/v1/ai/cpv/suggest",
        json={"text": "Servei de manteniment de la jardineria municipal"},
        headers=headers,
    )
    assert fallback.status_code == 200
    assert fallback.json()["source"] == "lexical"
    assert len(fallback.json()["suggestions"]) >= 1
