"""Lliurament de recordatoris: email, webhook, pendents i reavís de vençudes."""

from collections.abc import AsyncIterator
from datetime import date, timedelta
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.db import session_factory
from app.jobs.registry import JobContext
from app.modules.tasks import reminders as reminders_module
from app.modules.tasks.reminders import send_task_reminders
from tests.conftest import login_headers

TODAY = date.today()


class FakeSmtp:
    def __init__(self) -> None:
        self.sent: list[tuple[list[str], str]] = []

    async def send_mail(self, to: list[str], subject: str, body: str) -> None:
        self.sent.append((to, subject))


@pytest.fixture
async def world(make_user) -> AsyncIterator[dict[str, Any]]:  # type: ignore[no-untyped-def]
    tag = uuid4().hex[:8]
    data: dict[str, Any] = {"tag": tag}
    data["dm"] = await make_user("dept_manager")
    data["assignee"] = await make_user("employee")

    async with session_factory() as session:
        dept = (
            await session.execute(
                text("INSERT INTO departments (code, name) VALUES (:c, 'REM') RETURNING id"),
                {"c": f"RM-{tag}"},
            )
        ).scalar_one()
        for user in (data["dm"], data["assignee"]):
            await session.execute(
                text("INSERT INTO user_departments (user_id, department_id) VALUES (:u, :d)"),
                {"u": user.id, "d": dept},
            )
        contract = (
            await session.execute(
                text(
                    "INSERT INTO contracts (file_code, status, lot, subject) "
                    "VALUES (:f, 'Execució', '', :s) RETURNING id"
                ),
                {"f": f"REM-{tag}/1", "s": f"Recordatoris {tag}"},
            )
        ).scalar_one()
        await session.execute(
            text("INSERT INTO contract_departments (contract_id, department_id) VALUES (:c, :d)"),
            {"c": contract, "d": dept},
        )
        await session.commit()
        data.update(dept=dept, contract=contract)

    yield data

    async with session_factory() as session:
        await session.execute(
            text(
                "DELETE FROM tasks WHERE contract_id IN "
                "(SELECT id FROM contracts WHERE file_code LIKE :p)"
            ),
            {"p": f"REM-{tag}%"},
        )
        await session.execute(
            text("DELETE FROM contracts WHERE file_code LIKE :p"), {"p": f"REM-{tag}%"}
        )
        await session.execute(
            text("DELETE FROM departments WHERE code LIKE :p"), {"p": f"RM-{tag}"}
        )
        await session.commit()


async def _run_job() -> dict[str, Any]:
    async def _noop(_pct: int, _msg: str | None = None) -> None:
        return None

    result = await send_task_reminders(JobContext(job_id=uuid4(), payload=None, set_progress=_noop))
    assert result is not None
    return result


async def test_reminders_email_webhook_and_overdue(
    api_client: TestClient, world: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    dm = login_headers(api_client, world["dm"].email)
    tag = world["tag"]

    # Tasca amb recordatori email vençut (offset 7, venç d'aquí a 5 dies)
    # i webhook encara NO vençut (offset 0).
    created = api_client.post(
        "/api/v1/tasks",
        json={
            "title": f"Recordatori {tag}",
            "due_date": str(TODAY + timedelta(days=5)),
            "contract_id": world["contract"],
            "assignee_ids": [world["assignee"].id],
            "reminders": [
                {"offset_days": 7, "channel": "email"},
                {"offset_days": 0, "channel": "webhook"},
            ],
        },
        headers=dm,
    )
    assert created.status_code == 201, created.text
    task_id = created.json()["id"]

    # Tasca vençuda (reavís overdue).
    overdue = api_client.post(
        "/api/v1/tasks",
        json={
            "title": f"Vençuda {tag}",
            "due_date": str(TODAY - timedelta(days=3)),
            "contract_id": world["contract"],
            "assignee_ids": [world["assignee"].id],
        },
        headers=dm,
    ).json()

    fake = FakeSmtp()

    async def fake_smtp() -> FakeSmtp:
        return fake

    monkeypatch.setattr(reminders_module, "_smtp", fake_smtp)

    result = await _run_job()
    assert result["emails"] >= 1
    assert result["overdue_notified"] >= 1

    # L'email ha anat a l'assignat i el recordatori queda marcat.
    our_emails = [s for s in fake.sent if world["assignee"].email in s[0]]
    assert any(f"Recordatori {tag}" in subject for _, subject in our_emails)
    assert any(f"Vençuda {tag}" in subject for _, subject in our_emails)

    async with session_factory() as session:
        rows = (
            await session.execute(
                text("SELECT channel, sent_at FROM task_reminders WHERE task_id = :t ORDER BY id"),
                {"t": task_id},
            )
        ).all()
        by_channel = {r.channel: r.sent_at for r in rows}
        assert by_channel["email"] is not None  # enviat
        assert by_channel["webhook"] is None  # offset 0: encara no toca

        # Esdeveniment overdue a l'outbox.
        overdue_events = (
            await session.execute(
                text(
                    "SELECT count(*) FROM outbox_events WHERE event_type = 'task.overdue' "
                    "AND aggregate_id = :id"
                ),
                {"id": str(overdue["id"])},
            )
        ).scalar_one()
        assert overdue_events == 1

    # Segona execució: cap email duplicat (sent_at) ni reavís repetit (dedupe).
    before = len(fake.sent)
    result = await _run_job()
    our_new = [s for s in fake.sent[before:] if world["assignee"].email in s[0]]
    assert not our_new

    async with session_factory() as session:
        overdue_events = (
            await session.execute(
                text(
                    "SELECT count(*) FROM outbox_events WHERE event_type = 'task.overdue' "
                    "AND aggregate_id = :id"
                ),
                {"id": str(overdue["id"])},
            )
        ).scalar_one()
        assert overdue_events == 1  # sense duplicat


async def test_email_pending_without_smtp(
    api_client: TestClient, world: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    dm = login_headers(api_client, world["dm"].email)
    tag = world["tag"]
    created = api_client.post(
        "/api/v1/tasks",
        json={
            "title": f"Pendent smtp {tag}",
            "due_date": str(TODAY + timedelta(days=1)),
            "contract_id": world["contract"],
            "assignee_ids": [world["assignee"].id],
            "reminders": [{"offset_days": 3, "channel": "email"}],
        },
        headers=dm,
    )
    assert created.status_code == 201

    async def no_smtp() -> None:
        return None

    monkeypatch.setattr(reminders_module, "_smtp", no_smtp)
    result = await _run_job()
    assert result["smtp_enabled"] is False
    assert result["pending_smtp"] >= 1

    # El recordatori segueix pendent (s'enviarà quan hi hagi connector).
    async with session_factory() as session:
        sent = (
            await session.execute(
                text("SELECT sent_at FROM task_reminders WHERE task_id = :t"),
                {"t": created.json()["id"]},
            )
        ).scalar_one()
        assert sent is None
