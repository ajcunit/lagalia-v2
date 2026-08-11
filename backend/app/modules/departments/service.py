"""Casos d'ús de departaments: CRUD amb baixa lògica i auditoria."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.problems import Problem
from app.modules.audit.models import AuditActorType
from app.modules.audit.service import record_audit
from app.modules.departments import repository
from app.modules.departments.models import Department
from app.modules.departments.schemas import DepartmentCreate, DepartmentUpdate
from app.modules.users.models import User
from app.modules.users.service import RequestContext


def _not_found() -> Problem:
    return Problem(404, "Departament no trobat", "not-found")


async def _audit(
    session: AsyncSession,
    action: str,
    actor: User,
    department: Department,
    ctx: RequestContext,
    changed: list[str] | None = None,
) -> None:
    await record_audit(
        session,
        actor_type=AuditActorType.USER,
        action=action,
        success=True,
        actor_id=actor.id,
        resource_type="department",
        resource_id=str(department.id),
        ip=ctx.ip,
        user_agent=ctx.user_agent,
        trace_id=ctx.trace_id,
        details={"changed": changed} if changed else None,
    )


async def get_department(session: AsyncSession, department_id: int) -> Department:
    department = await repository.get_by_id(session, department_id)
    if department is None:
        raise _not_found()
    return department


async def create_department(
    session: AsyncSession, data: DepartmentCreate, actor: User, ctx: RequestContext
) -> Department:
    if await repository.get_by_code(session, data.code) is not None:
        raise Problem(409, "El codi ja existeix", "conflict")

    department = Department(code=data.code, name=data.name, description=data.description)
    session.add(department)
    await session.flush()
    await _audit(session, "departments.create", actor, department, ctx)
    await session.commit()
    return department


async def update_department(
    session: AsyncSession,
    department_id: int,
    data: DepartmentUpdate,
    actor: User,
    ctx: RequestContext,
) -> Department:
    department = await get_department(session, department_id)
    changes = data.model_dump(exclude_unset=True)

    if "code" in changes and changes["code"] != department.code:
        existing = await repository.get_by_code(session, changes["code"])
        if existing is not None and existing.id != department.id:
            raise Problem(409, "El codi ja existeix", "conflict")

    for field, value in changes.items():
        setattr(department, field, value)
    await session.flush()
    await _audit(session, "departments.update", actor, department, ctx, sorted(changes))
    await session.commit()
    return department


async def deactivate_department(
    session: AsyncSession, department_id: int, actor: User, ctx: RequestContext
) -> None:
    department = await get_department(session, department_id)
    department.active = False
    await session.flush()
    await _audit(session, "departments.deactivate", actor, department, ctx)
    await session.commit()
