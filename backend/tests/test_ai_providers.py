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


async def test_analyst_agent(api_client, make_user, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    from sqlalchemy import text as sql_text

    plain = await make_user("employee")
    auditor = await make_user("employee", can_audit=True)

    assert (
        api_client.post(
            "/api/v1/ai/analyses",
            json={"question": "quants contractes?"},
            headers=login_headers(api_client, plain.email),
        ).status_code
        == 403
    )

    async with session_factory() as session:
        await session.execute(
            sql_text(
                "INSERT INTO ai_provider_profiles "
                "(name, protocol, base_url, default_model, enabled) "
                "VALUES ('analyst-fake', 'openai_compatible', 'http://an.fake/v1', 'm', true)"
            )
        )
        await session.commit()

    calls = {"n": 0}

    def _sse(content: str) -> bytes:
        import json as _json

        chunk = _json.dumps({"choices": [{"delta": {"content": content}}]})
        return f"data: {chunk}\n\ndata: [DONE]\n\n".encode()

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(200, content=_sse('{"tool": "totals", "args": {}}'))
        body = request.read().decode()
        assert "<resultat" in body  # el resultat de l'eina ha arribat delimitat
        return httpx.Response(200, content=_sse("Hi ha **N** contractes segons totals."))

    monkeypatch.setattr(providers, "_transport", httpx.MockTransport(handler))
    response = api_client.post(
        "/api/v1/ai/analyses",
        json={"question": "Quants contractes tenim?"},
        headers=login_headers(api_client, auditor.email),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["answer_markdown"].startswith("Hi ha")
    assert body["steps"][0]["tool"] == "totals"
    assert "contracts" in body["steps"][0]["rows"]

    async with session_factory() as session:
        await session.execute(
            sql_text("DELETE FROM ai_provider_profiles WHERE name = 'analyst-fake'")
        )
        await session.commit()


async def test_stream_endpoint(api_client, make_user, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    from sqlalchemy import text as sql_text

    auditor = await make_user("employee", can_audit=True)
    async with session_factory() as session:
        await session.execute(
            sql_text(
                "INSERT INTO ai_provider_profiles "
                "(name, protocol, base_url, default_model, enabled) "
                "VALUES ('stream-fake', 'openai_compatible', 'http://st.fake/v1', 'm', true)"
            )
        )
        await session.commit()

    def handler(request: httpx.Request) -> httpx.Response:
        sse = (
            'data: {"choices":[{"delta":{"content":"# Inf"}}]}\n\n'
            'data: {"choices":[{"delta":{"content":"orme"}}],'
            '"usage":{"prompt_tokens":5,"completion_tokens":2}}\n\n'
            "data: [DONE]\n\n"
        )
        return httpx.Response(200, content=sse.encode())

    monkeypatch.setattr(providers, "_transport", httpx.MockTransport(handler))
    with api_client.stream(
        "POST",
        "/api/v1/ai/audit/report/stream",
        json={},
        headers=login_headers(api_client, auditor.email),
    ) as response:
        assert response.status_code == 200
        lines = [line for line in response.iter_lines() if line.strip()]
    import json as _json

    events = [_json.loads(line) for line in lines]
    text_out = "".join(e.get("text", "") for e in events if e["type"] == "delta")
    assert text_out == "# Informe"
    assert events[-1]["type"] == "done"

    async with session_factory() as session:
        await session.execute(
            sql_text("DELETE FROM ai_provider_profiles WHERE name = 'stream-fake'")
        )
        await session.commit()


async def test_scheduled_audit_report_never_crashes(monkeypatch: pytest.MonkeyPatch) -> None:
    """El job mensual reporta el problema en lloc de tombar el scheduler."""
    from sqlalchemy import text as sql_text

    from app.ai import scheduled_reports

    # Sense perfils actius ni destinataris: ha de retornar un resum, no petar.
    async with session_factory() as session:
        enabled = list(
            (
                await session.execute(sql_text("SELECT id FROM ai_provider_profiles WHERE enabled"))
            ).scalars()
        )
        await session.execute(sql_text("UPDATE ai_provider_profiles SET enabled = false"))
        await session.commit()
    try:
        result = await scheduled_reports.build_and_send()
        assert result["generated"] is False
        assert result["emailed"] == 0
        assert result["detail"]
    finally:
        async with session_factory() as session:
            if enabled:
                await session.execute(
                    sql_text("UPDATE ai_provider_profiles SET enabled = true WHERE id = ANY(:i)"),
                    {"i": enabled},
                )
                await session.commit()


async def test_scheduled_report_success_path_emits_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Camí d'èxit complet: el bug d'emit_event() només sortia aquí."""
    from sqlalchemy import text as sql_text

    from app.ai import scheduled_reports

    async with session_factory() as session:
        await session.execute(
            sql_text(
                "INSERT INTO ai_provider_profiles "
                "(name, protocol, base_url, default_model, enabled) "
                "VALUES ('report-fake', 'openai_compatible', 'http://rep.fake/v1', 'm', true)"
            )
        )
        await session.commit()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "# Informe mensual"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            },
        )

    monkeypatch.setattr(providers, "_transport", httpx.MockTransport(handler))
    result = await scheduled_reports.build_and_send()
    assert result["generated"] is True

    async with session_factory() as session:
        events = (
            await session.execute(
                sql_text(
                    "SELECT count(*) FROM outbox_events WHERE event_type = 'audit.report_ready'"
                )
            )
        ).scalar_one()
        assert events >= 1
        await session.execute(
            sql_text("DELETE FROM ai_provider_profiles WHERE name = 'report-fake'")
        )
        await session.commit()


async def test_recipients_parsing() -> None:
    from sqlalchemy import text as sql_text

    from app.ai import scheduled_reports

    async with session_factory() as session:
        await session.execute(
            sql_text(
                "INSERT INTO settings (key, value) VALUES (:k, :v) "
                "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value"
            ),
            {"k": scheduled_reports.RECIPIENTS_SETTING, "v": '"a@cunit.cat; b@cunit.cat, mal"'},
        )
        await session.commit()
    assert await scheduled_reports._recipients() == ["a@cunit.cat", "b@cunit.cat"]
    async with session_factory() as session:
        await session.execute(
            sql_text("DELETE FROM settings WHERE key = :k"),
            {"k": scheduled_reports.RECIPIENTS_SETTING},
        )
        await session.commit()
