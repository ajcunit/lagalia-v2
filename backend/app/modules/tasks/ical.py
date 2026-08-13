"""Feed iCal de tasques (specs/tasks-ui.md): subscripció des d'Outlook.

Autorització per clau opaca revocable per usuari (mai el JWT de sessió
per query string, 06 §2). El feed conté les tasques obertes visibles
per a l'usuari com a ASSIGNAT o creador.
"""

import secrets
from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.tasks.models import Task, TaskStatus, task_assignees
from app.modules.users.models import User


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


async def rotate_key(session: AsyncSession, user: User) -> str:
    """Genera (o regenera = revoca l'anterior) la clau del feed."""
    user.ical_key = secrets.token_urlsafe(32)[:48]
    await session.flush()
    return user.ical_key


async def revoke_key(session: AsyncSession, user: User) -> None:
    user.ical_key = None
    await session.flush()


async def feed_for_key(session: AsyncSession, key: str) -> str | None:
    """Retorna el VCALENDAR o None si la clau no és vàlida."""
    user = (
        await session.execute(select(User).where(User.ical_key == key, User.active))
    ).scalar_one_or_none()
    if user is None:
        return None

    stmt = (
        select(Task)
        .options(selectinload(Task.assignees))
        .where(
            Task.status.in_([TaskStatus.PENDING, TaskStatus.IN_PROGRESS]),
            or_(
                Task.created_by == user.id,
                Task.id.in_(
                    select(task_assignees.c.task_id).where(task_assignees.c.user_id == user.id)
                ),
            ),
        )
        .order_by(Task.due_date.asc())
        .limit(500)
    )
    tasks = list((await session.execute(stmt)).scalars())

    now = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//LAGALia//Tasques//CA",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_escape('LAGALia — Tasques')}",
    ]
    for task in tasks:
        due = task.due_date.strftime("%Y%m%d")
        summary = _escape(task.title)
        description = _escape(task.description or "")
        lines += [
            "BEGIN:VEVENT",
            f"UID:lagalia-task-{task.id}@cunit.cat",
            f"DTSTAMP:{now}",
            f"DTSTART;VALUE=DATE:{due}",
            f"SUMMARY:{summary}",
        ]
        if description:
            lines.append(f"DESCRIPTION:{description}")
        priority = {"high": 1, "normal": 5}.get(task.priority.value, 9)
        lines += [f"PRIORITY:{priority}", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
