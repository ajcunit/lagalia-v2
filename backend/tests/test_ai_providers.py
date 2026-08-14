"""Capa de proveïdors d'IA (specs/ai-providers.md)."""

import httpx
import pytest
from sqlalchemy import select

from app.ai import providers
from app.ai.models import AiProtocol, AiProviderProfile, AiRun
from app.core.db import session_factory
from tests.conftest import login_headers

pytestmark = pytest.mark.anyio


async def test_provider_admin_api(api_client, make_user) -> None:  # type: ignore[no-untyped-def]
    admin_user = await make_user("admin")
    employee = await make_user("employee")
    admin = login_headers(api_client, admin_user.email)

    # Només config:write.
    assert (
        api_client.get(
            "/api/v1/ai/providers", headers=login_headers(api_client, employee.email)
        ).status_code
        == 403
    )

    created = api_client.post(
        "/api/v1/ai/providers",
        json={
            "name": "Ollama local",
            "protocol": "openai_compatible",
            "base_url": "http://127.0.0.1:11434/v1",
            "default_model": "llama3",
        },
        headers=admin,
    )
    assert created.status_code == 201, created.text
    pid = created.json()["id"]
    assert created.json()["api_key_set"] is False

    # Clau write-only: mai torna a la resposta.
    keyed = api_client.put(
        f"/api/v1/ai/providers/{pid}/api-key", json={"api_key": "sk-secreta"}, headers=admin
    )
    assert keyed.status_code == 200
    assert keyed.json()["api_key_set"] is True
    assert "sk-secreta" not in keyed.text
    assert "sk-secreta" not in api_client.get("/api/v1/ai/providers", headers=admin).text

    # Healthcheck contra un port tancat → failing estructurat, mai 500.
    health = api_client.post(f"/api/v1/ai/providers/{pid}/actions/healthcheck", headers=admin)
    assert health.status_code == 200
    assert health.json()["status"] == "failing"

    assert api_client.delete(f"/api/v1/ai/providers/{pid}", headers=admin).status_code == 204


async def test_complete_records_ai_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer sk-x"
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "resposta"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            },
        )

    monkeypatch.setattr(providers, "_transport", httpx.MockTransport(handler))
    from app.core import crypto

    async with session_factory() as session:
        profile = AiProviderProfile(
            name="test-fake",
            protocol=AiProtocol.OPENAI_COMPATIBLE,
            base_url="http://fake.test/v1",
            api_key_encrypted=crypto.encrypt_value("sk-x"),
            default_model="fake-model",
        )
        session.add(profile)
        await session.commit()
        pid = profile.id

    result = await providers.complete(
        profile, [{"role": "user", "content": "hola"}], task="test.completion"
    )
    assert result.content == "resposta"
    assert result.output_tokens == 5

    async with session_factory() as session:
        run = (
            await session.execute(
                select(AiRun).where(AiRun.provider_profile_id == pid).order_by(AiRun.id.desc())
            )
        ).scalars().first()
        assert run is not None and run.status == "success"
        assert run.input_tokens == 10 and run.latency_ms is not None


async def test_ollama_and_gemini_adapters(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "llama3:8b"}]})
        if path == "/api/chat":
            return httpx.Response(
                200,
                json={
                    "message": {"role": "assistant", "content": "hola des d'ollama"},
                    "prompt_eval_count": 7,
                    "eval_count": 4,
                },
            )
        if path == "/v1beta/models":
            assert request.url.params["key"] == "g-key"
            return httpx.Response(200, json={"models": [{"name": "models/gemini-2.5-flash"}]})
        if path.endswith(":generateContent"):
            assert request.url.params["key"] == "g-key"
            return httpx.Response(
                200,
                json={
                    "candidates": [{"content": {"parts": [{"text": "hola des de gemini"}]}}],
                    "usageMetadata": {"promptTokenCount": 9, "candidatesTokenCount": 3},
                },
            )
        raise AssertionError(f"ruta inesperada: {path}")

    monkeypatch.setattr(providers, "_transport", httpx.MockTransport(handler))
    from app.core import crypto

    async with session_factory() as session:
        ollama = AiProviderProfile(
            name="test-ollama", protocol=AiProtocol.OLLAMA,
            base_url="http://fake.ollama:11434", default_model="llama3:8b",
        )
        gemini = AiProviderProfile(
            name="test-gemini", protocol=AiProtocol.GEMINI,
            base_url="https://fake.gemini", default_model="gemini-2.5-flash",
            api_key_encrypted=crypto.encrypt_value("g-key"),
        )
        session.add_all([ollama, gemini])
        await session.commit()

        assert await providers.list_models(ollama) == ["llama3:8b"]
        assert await providers.list_models(gemini) == ["gemini-2.5-flash"]

    o = await providers.complete(ollama, [{"role": "user", "content": "hola"}], task="t.o")
    assert o.content == "hola des d'ollama" and o.output_tokens == 4
    g = await providers.complete(
        gemini,
        [{"role": "system", "content": "sys"}, {"role": "user", "content": "hola"}],
        task="t.g",
    )
    assert g.content == "hola des de gemini" and g.input_tokens == 9


async def test_task_config_resolution(api_client, make_user) -> None:  # type: ignore[no-untyped-def]
    from app.ai import tasks as ai_tasks

    admin_user = await make_user("admin")
    admin = login_headers(api_client, admin_user.email)

    created = api_client.post(
        "/api/v1/ai/providers",
        json={
            "name": "task-fake",
            "protocol": "openai_compatible",
            "base_url": "http://task.fake/v1",
            "default_model": "base-model",
        },
        headers=admin,
    )
    pid = created.json()["id"]
    api_client.patch(f"/api/v1/ai/providers/{pid}", json={"enabled": True}, headers=admin)

    # Assigna cpv.rank a aquest perfil amb model específic.
    assert (
        api_client.put(
            "/api/v1/ai/tasks/cpv.rank",
            json={"provider_profile_id": pid, "model": "model-fi"},
            headers=admin,
        ).status_code
        == 200
    )
    assert (
        api_client.put(
            "/api/v1/ai/tasks/inventada", json={"provider_profile_id": pid}, headers=admin
        ).status_code
        == 404
    )

    listing = api_client.get("/api/v1/ai/tasks", headers=admin).json()["data"]
    rank = next(r for r in listing if r["task"] == "cpv.rank")
    assert rank["effective"]["model"] == "model-fi"
    extract = next(r for r in listing if r["task"] == "cpv.extract")
    assert extract["config"] is None  # sense config → fallback

    async with session_factory() as session:
        resolved = await ai_tasks.resolve(session, "cpv.rank")
        assert resolved.model == "model-fi"

    # Reset → torna al defecte.
    assert api_client.delete("/api/v1/ai/tasks/cpv.rank", headers=admin).status_code == 204
    async with session_factory() as session:
        resolved = await ai_tasks.resolve(session, "cpv.rank")
        assert resolved.model is None

    # Neteja: el perfil actiu no ha de contaminar altres tests de la bateria.
    assert api_client.delete(f"/api/v1/ai/providers/{pid}", headers=admin).status_code == 204


async def test_audit_report_agent(api_client, make_user, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    from sqlalchemy import text as sql_text

    plain = await make_user("employee")
    auditor = await make_user("employee", can_audit=True)

    assert (
        api_client.post(
            "/api/v1/ai/audit/report", json={}, headers=login_headers(api_client, plain.email)
        ).status_code
        == 403
    )

    async with session_factory() as session:
        await session.execute(
            sql_text(
                "INSERT INTO ai_provider_profiles "
                "(name, protocol, base_url, default_model, enabled) "
                "VALUES ('audit-fake', 'openai_compatible', 'http://audit.fake/v1', 'm', true)"
            )
        )
        await session.commit()

    def handler(request: httpx.Request) -> httpx.Response:
        body = request.read().decode()
        assert "<dades>" in body and "Centra't" in body
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "# Informe\n\nRiscos prioritzats."}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 50},
            },
        )

    monkeypatch.setattr(providers, "_transport", httpx.MockTransport(handler))
    response = api_client.post(
        "/api/v1/ai/audit/report",
        json={"custom_prompt": "Centra't en el fraccionament"},
        headers=login_headers(api_client, auditor.email),
    )
    assert response.status_code == 200, response.text
    assert response.json()["report_markdown"].startswith("# Informe")

    async with session_factory() as session:
        await session.execute(
            sql_text("DELETE FROM ai_provider_profiles WHERE name = 'audit-fake'")
        )
        await session.commit()
