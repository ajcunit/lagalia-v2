"""Motor central d'autorització (docs/06-seguretat.md §3).

La matriu de l'annex A2 és aquí com a DADES: el motor no coneix cap rol
fora de PERMISSION_MATRIX. Els routers només fan servir Authorize(action);
cap `if user.role == ...` enlloc més.
"""

import enum
from dataclasses import dataclass
from typing import Annotated, Literal

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.problems import Problem
from app.modules.audit.models import AuditActorType
from app.modules.audit.service import record_audit
from app.modules.users.dependencies import (
    CurrentSession,
    get_current_session,
    get_request_context,
)
from app.modules.users.models import User, UserRole
from app.modules.users.service import RequestContext


class Access(enum.StrEnum):
    """Tipus d'accés que la matriu A2 concedeix a una acció.

    MANAGED i ASSIGNED es materialitzen als resource loaders dels mòduls
    (Fase 1); el motor ja els distingeix i els exposa.
    """

    ALL = "all"  # sense restricció
    DEPT = "dept"  # dins l'abast departamental (A2 §3)
    MANAGED = "managed"  # només recursos dels quals és responsable
    ASSIGNED = "assigned"  # només recursos assignats a l'usuari


@dataclass(frozen=True)
class Grant:
    access: Access
    flag: Literal["can_audit", "can_plan"] | None = None


_ALL = Grant(Access.ALL)
_DEPT = Grant(Access.DEPT)

# Transcripció de docs/annexos/A2-matriu-permisos.md §2.
# Absència de rol = denegat. El test de taula de veritat en verifica
# cada cel·la de manera independent d'aquest diccionari.
PERMISSION_MATRIX: dict[str, dict[UserRole, Grant]] = {
    # Contractes
    "contracts:read": {
        UserRole.ADMIN: _ALL,
        UserRole.PROCUREMENT_MANAGER: _ALL,
        UserRole.DEPT_MANAGER: _DEPT,
        UserRole.EMPLOYEE: _DEPT,
    },
    "contracts:create": {UserRole.ADMIN: _ALL, UserRole.PROCUREMENT_MANAGER: _ALL},
    "contracts:update": {UserRole.ADMIN: _ALL, UserRole.PROCUREMENT_MANAGER: _ALL},
    "contracts:update_warning": {
        UserRole.ADMIN: _ALL,
        UserRole.PROCUREMENT_MANAGER: _ALL,
        UserRole.DEPT_MANAGER: _DEPT,
    },
    "contracts:assign": {UserRole.ADMIN: _ALL, UserRole.PROCUREMENT_MANAGER: _ALL},
    "contracts:bulk_assign": {UserRole.ADMIN: _ALL, UserRole.PROCUREMENT_MANAGER: _ALL},
    "contracts:close_alert": {
        UserRole.ADMIN: _ALL,
        UserRole.PROCUREMENT_MANAGER: _ALL,
        UserRole.DEPT_MANAGER: Grant(Access.MANAGED),
    },
    "contracts:enrich": {UserRole.ADMIN: _ALL, UserRole.PROCUREMENT_MANAGER: _ALL},
    "contracts:export": {
        UserRole.ADMIN: _ALL,
        UserRole.PROCUREMENT_MANAGER: _ALL,
        UserRole.DEPT_MANAGER: _DEPT,
        UserRole.EMPLOYEE: _DEPT,
    },
    "contracts:open_gestiona": {UserRole.ADMIN: _ALL, UserRole.PROCUREMENT_MANAGER: _ALL},
    # Menors
    "minor_contracts:read": {
        UserRole.ADMIN: _ALL,
        UserRole.PROCUREMENT_MANAGER: _ALL,
        UserRole.DEPT_MANAGER: _DEPT,
        UserRole.EMPLOYEE: _DEPT,
    },
    "minor_contracts:update": {UserRole.ADMIN: _ALL, UserRole.PROCUREMENT_MANAGER: _ALL},
    # Duplicats
    "duplicates:manage": {UserRole.ADMIN: _ALL, UserRole.PROCUREMENT_MANAGER: _ALL},
    # Sincronització
    "sync:execute": {UserRole.ADMIN: _ALL, UserRole.PROCUREMENT_MANAGER: _ALL},
    "sync:read": {UserRole.ADMIN: _ALL, UserRole.PROCUREMENT_MANAGER: _ALL},
    "association_rules:manage": {UserRole.ADMIN: _ALL, UserRole.PROCUREMENT_MANAGER: _ALL},
    # Organització
    "departments:read": {
        UserRole.ADMIN: _ALL,
        UserRole.PROCUREMENT_MANAGER: _ALL,
        UserRole.DEPT_MANAGER: _ALL,
        UserRole.EMPLOYEE: _ALL,
    },
    "departments:write": {UserRole.ADMIN: _ALL, UserRole.PROCUREMENT_MANAGER: _ALL},
    # ⚠️ Divergència v1→v2 (A2 §2): gestió d'usuaris només admin.
    "users:read": {UserRole.ADMIN: _ALL},
    "users:write": {UserRole.ADMIN: _ALL},
    "me:update": {
        UserRole.ADMIN: _ALL,
        UserRole.PROCUREMENT_MANAGER: _ALL,
        UserRole.DEPT_MANAGER: _ALL,
        UserRole.EMPLOYEE: _ALL,
    },
    # Configuració
    "config:read": {
        UserRole.ADMIN: _ALL,
        UserRole.PROCUREMENT_MANAGER: _ALL,
        UserRole.DEPT_MANAGER: _ALL,
        UserRole.EMPLOYEE: _ALL,
    },
    "config:write": {UserRole.ADMIN: _ALL},
    # Webhooks sortints: mateixa fila d'A2 que «escriure configuració».
    "webhooks:manage": {UserRole.ADMIN: _ALL},
    # Pla anual
    "plan:read": {
        UserRole.ADMIN: _ALL,
        UserRole.PROCUREMENT_MANAGER: _ALL,
        UserRole.DEPT_MANAGER: _DEPT,
        UserRole.EMPLOYEE: Grant(Access.DEPT, flag="can_plan"),
    },
    "plan:write": {
        UserRole.ADMIN: _ALL,
        UserRole.PROCUREMENT_MANAGER: _ALL,
        UserRole.DEPT_MANAGER: Grant(Access.DEPT, flag="can_plan"),
        UserRole.EMPLOYEE: Grant(Access.DEPT, flag="can_plan"),
    },
    "plan:approve": {UserRole.ADMIN: _ALL},
    # Auditoria de contractació (red flags + IA)
    "audit:run": {
        UserRole.ADMIN: _ALL,
        UserRole.PROCUREMENT_MANAGER: Grant(Access.ALL, flag="can_audit"),
        UserRole.DEPT_MANAGER: Grant(Access.DEPT, flag="can_audit"),
        UserRole.EMPLOYEE: Grant(Access.DEPT, flag="can_audit"),
    },
    # Auditoria de seguretat (nova v2)
    "audit_log:read": {UserRole.ADMIN: _ALL},
    # Tasques (nou v2)
    "tasks:read": {
        UserRole.ADMIN: _ALL,
        UserRole.PROCUREMENT_MANAGER: _ALL,
        UserRole.DEPT_MANAGER: _DEPT,
        UserRole.EMPLOYEE: Grant(Access.ASSIGNED),
    },
    "tasks:write": {
        UserRole.ADMIN: _ALL,
        UserRole.PROCUREMENT_MANAGER: _ALL,
        UserRole.DEPT_MANAGER: _DEPT,
    },
    "tasks:update_status": {
        UserRole.ADMIN: _ALL,
        UserRole.PROCUREMENT_MANAGER: _ALL,
        UserRole.DEPT_MANAGER: Grant(Access.ASSIGNED),
        UserRole.EMPLOYEE: Grant(Access.ASSIGNED),
    },
    # Revisió legal (nova v2)
    "compliance:run": {
        UserRole.ADMIN: _ALL,
        UserRole.PROCUREMENT_MANAGER: _ALL,
        UserRole.DEPT_MANAGER: _DEPT,
    },
    "compliance:manage": {UserRole.ADMIN: _ALL},
    # Generador documental, favorits, CPV, SuperBuscador
    "tools:use": {
        UserRole.ADMIN: _ALL,
        UserRole.PROCUREMENT_MANAGER: _ALL,
        UserRole.DEPT_MANAGER: _ALL,
        UserRole.EMPLOYEE: _ALL,
    },
    # Sistema (readiness amb estat de dependències)
    "system:read": {UserRole.ADMIN: _ALL},
}

# Rols amb abast complet i dret a la Vista Admin (A2 §3).
_FULL_SCOPE_ROLES = frozenset({UserRole.ADMIN, UserRole.PROCUREMENT_MANAGER})


def evaluate(user: User, action: str) -> Grant | None:
    """Retorna el Grant efectiu, o None si l'acció és denegada."""
    grant = PERMISSION_MATRIX.get(action, {}).get(user.role)
    if grant is None:
        return None
    if grant.flag is not None and not getattr(user, grant.flag):
        return None
    return grant


def allowed_actions(user: User) -> list[str]:
    return sorted(action for action in PERMISSION_MATRIX if evaluate(user, action))


@dataclass(frozen=True)
class ScopeInfo:
    type: Literal["all", "departments"]
    department_ids: list[int] | None = None


def scope_for(user: User) -> ScopeInfo:
    if user.role in _FULL_SCOPE_ROLES:
        return ScopeInfo(type="all")
    # Sense departaments: llista buida, mai «tot» (A2 §3).
    return ScopeInfo(type="departments", department_ids=[d.id for d in user.departments])


def can_switch_view(user: User) -> bool:
    return user.role in _FULL_SCOPE_ROLES


async def _audit_denial(
    session: AsyncSession, user: User, action: str, ctx: RequestContext
) -> None:
    await record_audit(
        session,
        actor_type=AuditActorType.USER,
        action="authz.denied",
        success=False,
        actor_id=user.id,
        resource_type="action",
        resource_id=action,
        ip=ctx.ip,
        user_agent=ctx.user_agent,
        trace_id=ctx.trace_id,
    )
    await session.commit()


def _forbidden() -> Problem:
    return Problem(403, "Sense permís per a aquesta acció", "forbidden")


@dataclass(frozen=True)
class AuthzContext:
    user: User
    action: str
    access: Access
    scope: ScopeInfo


class Authorize:
    """Dependency d'endpoint: Authorize("contracts:read").

    Tota denegació queda auditada (regla 4 de l'A2).
    """

    def __init__(self, action: str) -> None:
        if action not in PERMISSION_MATRIX:
            raise ValueError(f"Acció desconeguda a la matriu A2: {action}")
        self.action = action

    async def __call__(
        self,
        current: Annotated[CurrentSession, Depends(get_current_session)],
        session: Annotated[AsyncSession, Depends(get_session)],
        ctx: Annotated[RequestContext, Depends(get_request_context)],
    ) -> AuthzContext:
        grant = evaluate(current.user, self.action)
        if grant is None:
            await _audit_denial(session, current.user, self.action, ctx)
            raise _forbidden()
        return AuthzContext(
            user=current.user,
            action=self.action,
            access=grant.access,
            scope=scope_for(current.user),
        )


async def resolve_view_scope(
    session: AsyncSession, user: User, view: str, ctx: RequestContext
) -> ScopeInfo:
    """Valida el paràmetre ?view=user|all contra el rol REAL (mai de confiança).

    `view=all` sense dret a Vista Admin → 403 auditat.
    """
    if view == "all":
        if not can_switch_view(user):
            await _audit_denial(session, user, "view:all", ctx)
            raise _forbidden()
        return ScopeInfo(type="all")
    if user.role in _FULL_SCOPE_ROLES:
        # Vista Usuari demanada per un rol d'abast complet.
        return ScopeInfo(type="departments", department_ids=[d.id for d in user.departments])
    return scope_for(user)
