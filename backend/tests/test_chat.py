"""Xat general i per expedient (specs/chat.md, B-016)."""

import json
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.core.db import session_factory
from tests.conftest import login_headers

pytestmark = pytest.mark.anyio


async def test_chat_threads_and_stream(  # type: ignore[no-untyped-def]
    monkeypatch: pytest.MonkeyPatch, api_client, make_user
) -> None:
    admin_user = await make_user("admin")
    employee = await make_user("employee")
    dm_other = await make_user("dept_manager")
    admin = login_headers(api_client, admin_user.email)

    # General: cal audit:run per crear (employee → 403).
    assert (
        api_client.post(
            "/api/v1/chat/threads",
            json={"scope": "general"},
            headers=login_headers(api_client, employee.email),
        ).status_code
        == 403
    )
    created = api_client.post(
        "/api/v1/chat/threads", json={"scope": "general"}, headers=admin
    )
    assert created.status_code == 201, created.text
    thread_id = created.json()["id"]

    # Propietat: un altre usuari no veu el fil (404).
    assert (
        api_client.get(
            f"/api/v1/chat/threads/{thread_id}",
            headers=login_headers(api_client, dm_other.email),
        ).status_code
        == 404
    )

    # Stream general amb agent simulat: persisteix pregunta i resposta.
    async def fake_answer(session, question, *, history=None, scope=None, user_id=None, trace_id=None):  # type: ignore[no-untyped-def]
        assert isinstance(history, list)
        yield {"type": "thinking", "text": "pensant"}
        yield {"type": "delta", "text": "Resposta de prova."}
        yield {"type": "done"}

    monkeypatch.setattr("app.modules.chat.router.analyst_agent.answer_events", fake_answer)
    response = api_client.post(
        f"/api/v1/chat/threads/{thread_id}/messages/stream",
        json={"content": "Quants contractes tenim?"},
        headers=admin,
    )
    assert response.status_code == 200, response.text
    events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
    kinds = [e["type"] for e in events]
    assert "delta" in kinds and kinds[-1] == "done"

    detail = api_client.get(f"/api/v1/chat/threads/{thread_id}", headers=admin)
    assert detail.status_code == 200
    messages = detail.json()["messages"]
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert messages[1]["content"] == "Resposta de prova."
    assert detail.json()["thread"]["title"].startswith("Quants contractes")

    # Segon torn: l'historial arriba a l'agent.
    seen_history: list = []

    async def fake_answer2(session, question, *, history=None, scope=None, user_id=None, trace_id=None):  # type: ignore[no-untyped-def]
        seen_history.extend(history or [])
        yield {"type": "delta", "text": "Segona resposta."}
        yield {"type": "done"}

    monkeypatch.setattr("app.modules.chat.router.analyst_agent.answer_events", fake_answer2)
    api_client.post(
        f"/api/v1/chat/threads/{thread_id}/messages/stream",
        json={"content": "I per import?"},
        headers=admin,
    )
    assert len(seen_history) == 2  # pregunta + resposta del primer torn

    # Llistat propi filtrat per scope.
    listing = api_client.get(
        "/api/v1/chat/threads", params={"scope": "general"}, headers=admin
    )
    assert any(row["id"] == thread_id for row in listing.json()["data"])

    # Esborrat en cascada.
    assert (
        api_client.delete(f"/api/v1/chat/threads/{thread_id}", headers=admin).status_code
        == 204
    )
    async with session_factory() as session:
        remaining = (
            await session.execute(
                text("SELECT count(*) FROM chat_messages WHERE thread_id = :t"),
                {"t": thread_id},
            )
        ).scalar_one()
    assert remaining == 0


async def test_chat_contract_scope(  # type: ignore[no-untyped-def]
    monkeypatch: pytest.MonkeyPatch, api_client, make_user
) -> None:
    admin_user = await make_user("admin")
    dm_other = await make_user("dept_manager")
    admin = login_headers(api_client, admin_user.email)

    tag = uuid4().hex[:8]
    async with session_factory() as session:
        dept_a = (
            await session.execute(
                text("INSERT INTO departments (code, name) VALUES (:c, 'XatA') RETURNING id"),
                {"c": f"XA-{tag}"},
            )
        ).scalar_one()
        dept_b = (
            await session.execute(
                text("INSERT INTO departments (code, name) VALUES (:c, 'XatB') RETURNING id"),
                {"c": f"XB-{tag}"},
            )
        ).scalar_one()
        await session.execute(
            text("INSERT INTO user_departments (user_id, department_id) VALUES (:u, :d)"),
            {"u": dm_other.id, "d": dept_a},
        )
        contract_id = (
            await session.execute(
                text(
                    "INSERT INTO contracts (file_code, status, lot, subject) "
                    "VALUES (:f, 'Formalització', '', 'Expedient de xat') RETURNING id"
                ),
                {"f": f"XAT/{tag}"},
            )
        ).scalar_one()
        await session.execute(
            text("INSERT INTO contract_departments (contract_id, department_id) VALUES (:c, :d)"),
            {"c": contract_id, "d": dept_b},
        )
        await session.commit()

    # contract_id obligatori; contracte fora d'abast → 404.
    assert (
        api_client.post(
            "/api/v1/chat/threads", json={"scope": "contract"}, headers=admin
        ).status_code
        == 422
    )
    assert (
        api_client.post(
            "/api/v1/chat/threads",
            json={"scope": "contract", "contract_id": contract_id},
            headers=login_headers(api_client, dm_other.email),
        ).status_code
        == 404
    )

    created = api_client.post(
        "/api/v1/chat/threads",
        json={"scope": "contract", "contract_id": contract_id},
        headers=admin,
    )
    assert created.status_code == 201, created.text
    thread_id = created.json()["id"]

    # Stream d'expedient amb agent simulat: emet fonts, es persisteixen i el
    # filtre per document arriba a l'agent.
    seen_document_ids: list = []

    async def fake_contract_events(  # type: ignore[no-untyped-def]
        session, cid, question, *, history=None, document_id=None, user_id=None, trace_id=None
    ):
        assert cid == contract_id
        seen_document_ids.append(document_id)
        yield {"type": "sources", "sources": [{"title": "PPT neteja", "doc_type": "PPT"}]}
        yield {"type": "delta", "text": "Segons el PPT, la garantia és del 5%."}

    monkeypatch.setattr(
        "app.modules.chat.router.chat_agent.contract_chat_events", fake_contract_events
    )
    response = api_client.post(
        f"/api/v1/chat/threads/{thread_id}/messages/stream",
        json={"content": "Quina garantia hi ha?", "document_id": 4242},
        headers=admin,
    )
    assert seen_document_ids == [4242]
    assert response.status_code == 200, response.text
    events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
    assert any(e["type"] == "sources" for e in events)

    detail = api_client.get(f"/api/v1/chat/threads/{thread_id}", headers=admin)
    assistant = detail.json()["messages"][1]
    assert assistant["sources"] == [{"title": "PPT neteja", "doc_type": "PPT"}]

    # Neteja (el contracte arrossega fils i missatges per CASCADE).
    async with session_factory() as session:
        await session.execute(text("DELETE FROM contracts WHERE id = :i"), {"i": contract_id})
        await session.execute(
            text("DELETE FROM departments WHERE id IN (:a, :b)"), {"a": dept_a, "b": dept_b}
        )
        await session.commit()
