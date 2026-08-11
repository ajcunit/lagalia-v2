"""Casos d'ús de gestió d'usuaris (CRUD admin) i perfil propi.

Separat del servei d'autenticació (service.py) per mantenir cada fitxer
en un sol cas d'ús. La baixa és sempre lògica i tanca les sessions.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import crypto
from app.core.problems import Problem
from app.core.security import hash_password
from app.modules.audit.models import AuditActorType
from app.modules.audit.service import record_audit
from app.modules.departments import repository as departments_repository
from app.modules.departments.models import Department
from app.modules.users import repository
from app.modules.users.models import User
from app.modules.users.schemas import MeUpdate, UserCreate, UserUpdate
from app.modules.users.service import RequestContext


def _not_found() -> Problem:
    return Problem(404, "Usuari no trobat", "not-found")


def _email_conflict() -> Problem:
    return Problem(409, "El correu ja existeix", "conflict")


async def _audit(
    session: AsyncSession,
    action: str,
    actor: User,
    subject_id: int,
    ctx: RequestContext,
    changed: list[str] | None = None,
) -> None:
    await record_audit(
        session,
        actor_type=AuditActorType.USER,
        action=action,
        success=True,
        actor_id=actor.id,
        resource_type="user",
        resource_id=str(subject_id),
        ip=ctx.ip,
        user_agent=ctx.user_agent,
        trace_id=ctx.trace_id,
        # Només els NOMS dels camps canviats: mai valors (dades personals).
        details={"changed": changed} if changed else None,
    )


async def _load_departments(session: AsyncSession, ids: list[int]) -> list[Department]:
    departments = await departments_repository.get_many(session, ids)
    if len(departments) != len(set(ids)):
        raise Problem(422, "Algun departament no existeix", "validation")
    return departments


async def get_user(session: AsyncSession, user_id: int) -> User:
    user = await repository.get_user_by_id(session, user_id)
    if user is None:
        raise _not_found()
    return user


async def create_user(
    session: AsyncSession, data: UserCreate, actor: User, ctx: RequestContext
) -> User:
    if await repository.get_user_by_email(session, data.email) is not None:
        raise _email_conflict()

    user = User(
        name=data.name,
        email=data.email,
        role=data.role,
        password_hash=hash_password(data.password) if data.password else None,
        can_audit=data.can_audit,
        can_plan=data.can_plan,
        departments=await _load_departments(session, data.department_ids),
    )
    session.add(user)
    await session.flush()
    await _audit(session, "users.create", actor, user.id, ctx)
    await session.commit()
    return user


async def update_user(
    session: AsyncSession, user_id: int, data: UserUpdate, actor: User, ctx: RequestContext
) -> User:
    user = await get_user(session, user_id)
    changes = data.model_dump(exclude_unset=True)

    if "department_ids" in changes:
        user.departments = await _load_departments(session, changes.pop("department_ids"))
    if "password" in changes:
        user.password_hash = hash_password(changes.pop("password"))
    deactivating = changes.get("active") is False and user.active
    for field, value in changes.items():
        setattr(user, field, value)

    if deactivating:
        # Mateixa garantia que DELETE: la desactivació tanca les sessions.
        await repository.revoke_all_user_tokens(session, user.id)

    await session.flush()
    changed = sorted(set(data.model_dump(exclude_unset=True)))
    await _audit(session, "users.update", actor, user.id, ctx, changed)
    await session.commit()
    return user


async def deactivate_user(
    session: AsyncSession, user_id: int, actor: User, ctx: RequestContext
) -> None:
    user = await get_user(session, user_id)
    user.active = False
    await repository.revoke_all_user_tokens(session, user.id)
    await session.flush()
    await _audit(session, "users.deactivate", actor, user.id, ctx)
    await session.commit()


async def update_me(session: AsyncSession, user: User, data: MeUpdate, ctx: RequestContext) -> User:
    changes = data.model_dump(exclude_unset=True)

    if "password" in changes:
        if user.password_hash is None:
            raise Problem(
                422,
                "Un usuari de directori no pot tenir contrasenya local",
                "validation",
            )
        user.password_hash = hash_password(changes.pop("password"))
    if "dni" in changes:
        dni = changes.pop("dni")
        user.dni_encrypted = crypto.encrypt_value(dni) if dni else None
    if "name" in changes:
        user.name = changes.pop("name")

    session.add(user)
    await session.flush()
    changed = sorted(set(data.model_dump(exclude_unset=True)))
    await _audit(session, "me.update", user, user.id, ctx, changed)
    await session.commit()
    return user
