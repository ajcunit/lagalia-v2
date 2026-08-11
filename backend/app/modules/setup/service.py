"""Inicialització del sistema: primer admin + configuració per defecte.

Concurrent-safe: advisory lock transaccional i re-comprovació del
comptador d'usuaris dins de la mateixa transacció.
"""

from datetime import UTC, datetime

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.problems import Problem
from app.core.security import hash_password
from app.modules.audit.models import AuditActorType
from app.modules.audit.service import record_audit
from app.modules.config.models import Setting
from app.modules.setup.schemas import InitializeRequest
from app.modules.users.models import User, UserRole
from app.modules.users.service import RequestContext

_SETUP_LOCK_KEY = 420_002


async def count_users(session: AsyncSession) -> int:
    return (await session.execute(select(func.count()).select_from(User))).scalar_one()


async def needs_setup(session: AsyncSession) -> bool:
    return await count_users(session) == 0


def _default_settings(data: InitializeRequest) -> list[Setting]:
    seeds = [
        Setting(
            key="setup.completed_at",
            value=datetime.now(UTC).isoformat(),
            description="Moment de la inicialització del sistema",
        )
    ]
    if data.organization_name:
        seeds.append(
            Setting(key="org.name", value=data.organization_name, description="Nom de l'ens")
        )
    if data.ine10_code:
        seeds.append(
            Setting(key="org.ine10_code", value=data.ine10_code, description="Codi INE10 de l'ens")
        )
    return seeds


async def initialize(session: AsyncSession, data: InitializeRequest, ctx: RequestContext) -> User:
    # Serialitza inicialitzacions concurrents; la comprovació va DINS del lock.
    await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _SETUP_LOCK_KEY})

    if not await needs_setup(session):
        await record_audit(
            session,
            actor_type=AuditActorType.SYSTEM,
            action="setup.initialize",
            success=False,
            resource_type="system",
            ip=ctx.ip,
            user_agent=ctx.user_agent,
            trace_id=ctx.trace_id,
        )
        await session.commit()
        raise Problem(403, "El sistema ja està inicialitzat", "already-initialized")

    admin = User(
        name=data.name,
        email=data.email,
        role=UserRole.ADMIN,
        password_hash=hash_password(data.password),
        departments=[],  # evita lazy load async en serialitzar la resposta
    )
    session.add(admin)
    for setting in _default_settings(data):
        session.add(setting)
    await session.flush()

    await record_audit(
        session,
        actor_type=AuditActorType.USER,
        action="setup.initialize",
        success=True,
        actor_id=admin.id,
        resource_type="system",
        ip=ctx.ip,
        user_agent=ctx.user_agent,
        trace_id=ctx.trace_id,
    )
    await session.commit()
    return admin
