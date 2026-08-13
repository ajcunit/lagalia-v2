"""Job tasks.reminders (specs/task-reminders.md): lliurament de recordatoris."""

from datetime import UTC, date, datetime, timedelta
from typing import Any

import structlog
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.db import session_factory
from app.integrations import hub
from app.integrations.base import ConnectorError
from app.integrations.smtp.connector import SmtpConnector
from app.jobs.registry import JobContext, job
from app.modules.tasks.models import Task, TaskReminder, TaskStatus
from app.modules.webhooks.service import emit_event, enqueue_dispatch

logger = structlog.get_logger()

_OPEN = (TaskStatus.PENDING, TaskStatus.IN_PROGRESS)


async def _smtp() -> SmtpConnector | None:
    """Connector smtp actiu, o None (els emails queden pendents)."""
    async with session_factory() as session:
        record = await hub.ensure_registered(session, "smtp")
        if not record.enabled:
            await session.commit()
            return None
        connector = await hub.get_connector(session, "smtp")
        await session.commit()
    return connector if isinstance(connector, SmtpConnector) else None


def _task_email(task: Task, *, overdue: bool) -> tuple[str, str]:
    subject = (
        f"[LAGALia] Tasca vençuda: {task.title}"
        if overdue
        else f"[LAGALia] Recordatori: {task.title}"
    )
    subject_line = "vençuda des del" if overdue else "venç el"
    body = (
        f"Tasca: {task.title}\n"
        f"Tipus: {task.task_type.value}\n"
        f"Venciment: {subject_line} {task.due_date.strftime('%d/%m/%Y')}\n"
    )
    if task.description:
        body += f"\n{task.description}\n"
    body += "\nGestiona-la a LAGALia (secció Tasques)."
    return subject, body


def _emails(task: Task) -> list[str]:
    return [u.email for u in task.assignees if u.email]


async def _send_due_reminders(
    session: AsyncSession, smtp: SmtpConnector | None, today: date
) -> dict[str, int]:
    counters = {"emails": 0, "webhooks": 0, "pending_smtp": 0, "failed": 0}
    reminders = list(
        (
            await session.execute(
                select(TaskReminder)
                .join(Task, Task.id == TaskReminder.task_id)
                .options(
                    selectinload(TaskReminder.task).selectinload(Task.assignees),
                )
                .where(
                    TaskReminder.sent_at.is_(None),
                    Task.status.in_(_OPEN),
                )
                .limit(500)
            )
        ).scalars()
    )
    for reminder in reminders:
        task = reminder.task
        if task.due_date - timedelta(days=reminder.offset_days) > today:
            continue  # encara no toca

        if reminder.channel.value == "webhook":
            await emit_event(
                session,
                event_type="task.due_soon",
                aggregate="task",
                aggregate_id=task.id,
                data={
                    "title": task.title,
                    "task_type": task.task_type.value,
                    "due_date": str(task.due_date),
                    "offset_days": reminder.offset_days,
                    "contract_id": task.contract_id,
                    "minor_contract_id": task.minor_contract_id,
                    "assignees": [u.name for u in task.assignees],
                },
            )
            reminder.sent_at = datetime.now(UTC)
            counters["webhooks"] += 1
            continue

        # canal email
        recipients = _emails(task)
        if smtp is None or not recipients:
            counters["pending_smtp"] += 1
            continue
        subject, body = _task_email(task, overdue=False)
        try:
            await smtp.send_mail(recipients, subject, body)
            reminder.sent_at = datetime.now(UTC)
            counters["emails"] += 1
        except ConnectorError as exc:
            counters["failed"] += 1
            logger.warning("reminder_email_failed", task_id=task.id, error=str(exc))
    await session.flush()
    return counters


async def _notify_overdue(session: AsyncSession, smtp: SmtpConnector | None, today: date) -> int:
    """Reavís diari de tasques vençudes (dedupe per tasca i dia a Redis)."""
    overdue_tasks = list(
        (
            await session.execute(
                select(Task)
                .options(selectinload(Task.assignees))
                .where(Task.status.in_(_OPEN), Task.due_date < today)
                .limit(500)
            )
        ).scalars()
    )
    if not overdue_tasks:
        return 0

    notified = 0
    redis = Redis.from_url(settings.redis_url)
    try:
        for task in overdue_tasks:
            fresh = await redis.set(
                f"task:overdue:{task.id}:{today.isoformat()}", "1", nx=True, ex=20 * 3600
            )
            if not fresh:
                continue  # ja avisada avui
            await emit_event(
                session,
                event_type="task.overdue",
                aggregate="task",
                aggregate_id=task.id,
                data={
                    "title": task.title,
                    "task_type": task.task_type.value,
                    "due_date": str(task.due_date),
                    "days_overdue": (today - task.due_date).days,
                    "contract_id": task.contract_id,
                    "minor_contract_id": task.minor_contract_id,
                },
            )
            if smtp is not None and (recipients := _emails(task)):
                subject, body = _task_email(task, overdue=True)
                try:
                    await smtp.send_mail(recipients, subject, body)
                except ConnectorError as exc:
                    logger.warning("overdue_email_failed", task_id=task.id, error=str(exc))
            notified += 1
    finally:
        await redis.aclose()
    await session.flush()
    return notified


@job("tasks.reminders")
async def send_task_reminders(ctx: JobContext) -> dict[str, Any]:
    today = datetime.now(UTC).date()
    smtp = await _smtp()
    async with session_factory() as session:
        counters = await _send_due_reminders(session, smtp, today)
        overdue = await _notify_overdue(session, smtp, today)
        await session.commit()
    await enqueue_dispatch()
    result = {**counters, "overdue_notified": overdue, "smtp_enabled": smtp is not None}
    logger.info("task_reminders_sent", **result)
    return result
