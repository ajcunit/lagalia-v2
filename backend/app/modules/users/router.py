"""Endpoints d'autenticació i perfil. Prims: la lògica és al servei."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import authz
from app.core.config import settings
from app.core.db import get_session
from app.core.pagination import PageMeta
from app.core.problems import Problem
from app.core.ratelimit import enforce_rate_limit, parse_rate
from app.modules.users import management, repository, service
from app.modules.users.dependencies import (
    CurrentSession,
    get_current_session,
    get_request_context,
)
from app.modules.users.models import UserRole
from app.modules.users.schemas import (
    LoginRequest,
    MeUpdate,
    MyPermissionsResponse,
    PagedUsersResponse,
    PermissionScope,
    RefreshRequest,
    TokenPairResponse,
    UserCreate,
    UserResponse,
    UserUpdate,
)
from app.modules.users.service import RequestContext

router = APIRouter()

# 20/h per compte, a més del límit per IP (docs/06-seguretat.md §5).
_ACCOUNT_LIMIT = (20, 3600)

SessionDep = Annotated[AsyncSession, Depends(get_session)]
ContextDep = Annotated[RequestContext, Depends(get_request_context)]


@router.post("/auth/login", tags=["auth"], operation_id="login")
async def login(body: LoginRequest, session: SessionDep, ctx: ContextDep) -> TokenPairResponse:
    ip_limit, ip_window = parse_rate(settings.rate_limit_login)
    await enforce_rate_limit("login-ip", ctx.ip or "unknown", ip_limit, ip_window)
    await enforce_rate_limit("login-account", body.email.lower(), *_ACCOUNT_LIMIT)
    return await service.login(session, body.email, body.password, ctx)


@router.post("/auth/refresh", tags=["auth"], operation_id="refreshSession")
async def refresh_session(
    body: RefreshRequest, session: SessionDep, ctx: ContextDep
) -> TokenPairResponse:
    ip_limit, ip_window = parse_rate(settings.rate_limit_login)
    await enforce_rate_limit("refresh-ip", ctx.ip or "unknown", ip_limit, ip_window)
    return await service.refresh(session, body.refresh_token, ctx)


@router.post("/auth/logout", tags=["auth"], operation_id="logout", status_code=204)
async def logout(
    current: Annotated[CurrentSession, Depends(get_current_session)],
    session: SessionDep,
    ctx: ContextDep,
) -> None:
    await service.logout(session, current.user, current.session_id, ctx)


@router.get("/me", tags=["me"], operation_id="getMe")
async def get_me(
    current: Annotated[CurrentSession, Depends(get_current_session)],
) -> UserResponse:
    return UserResponse.from_user(current.user)


@router.get("/me/permissions", tags=["me"], operation_id="getMyPermissions")
async def get_my_permissions(
    current: Annotated[CurrentSession, Depends(get_current_session)],
) -> MyPermissionsResponse:
    from app.core import modules as module_flags

    scope = authz.scope_for(current.user)
    return MyPermissionsResponse(
        role=current.user.role,
        actions=authz.allowed_actions(current.user),
        scope=PermissionScope(type=scope.type, department_ids=scope.department_ids),
        can_switch_view=authz.can_switch_view(current.user),
        disabled_modules=sorted(await module_flags.disabled_modules()),
    )


class NoticesResponse(BaseModel):
    """Comptadors de la barra d'avisos (specs/view-selector.md)."""

    tasks_open: int
    tasks_overdue: int
    contracts_expiring: int
    contracts_pending_review: int


@router.get("/me/notices", tags=["me"], operation_id="getMyNotices")
async def get_my_notices(
    session: SessionDep,
    current: Annotated[CurrentSession, Depends(get_current_session)],
    ctx: ContextDep,
    view: Annotated[str, Query(pattern=r"^(user|all|dept:[0-9]{1,10})$")] = "user",
) -> NoticesResponse:
    """Avisos per a la barra superior: tasques pròpies obertes/vençudes i
    contractes amb avís de venciment o pendents de revisió dins la vista."""
    from sqlalchemy import text as sql_text

    scope = await authz.resolve_view_scope(session, current.user, view, ctx)

    tasks = (
        await session.execute(
            sql_text(
                "SELECT count(*) FILTER (WHERE t.status IN ('pending', 'in_progress')) AS open, "
                "count(*) FILTER (WHERE t.status IN ('pending', 'in_progress') "
                "AND t.due_date < CURRENT_DATE) AS overdue "
                "FROM tasks t JOIN task_assignees a ON a.task_id = t.id "
                "WHERE a.user_id = :uid"
            ),
            {"uid": current.user.id},
        )
    ).one()

    scope_sql = ""
    params: dict[str, object] = {}
    if scope.type == "departments":
        scope_sql = (
            " AND c.id IN (SELECT contract_id FROM contract_departments "
            "WHERE department_id = ANY(:deps))"
        )
        params["deps"] = list(scope.department_ids or [])
    contracts = (
        await session.execute(
            sql_text(
                "SELECT count(*) FILTER (WHERE c.expiry_warning) AS expiring, "
                "count(*) FILTER (WHERE c.internal_status = 'pending_review') AS pending "
                f"FROM contracts c WHERE true{scope_sql}"
            ),
            params,
        )
    ).one()

    return NoticesResponse(
        tasks_open=int(tasks.open or 0),
        tasks_overdue=int(tasks.overdue or 0),
        contracts_expiring=int(contracts.expiring or 0),
        contracts_pending_review=int(contracts.pending or 0),
    )


@router.patch("/me", tags=["me"], operation_id="updateMe")
async def update_me(
    body: MeUpdate,
    authz_ctx: Annotated[authz.AuthzContext, Depends(authz.Authorize("me:update"))],
    session: SessionDep,
    ctx: ContextDep,
) -> UserResponse:
    user = await management.update_me(session, authz_ctx.user, body, ctx)
    return UserResponse.from_user(user)


def _parse_sort(sort: str) -> tuple[str, bool]:
    descending = sort.startswith("-")
    field = sort.removeprefix("-")
    if field not in repository.SORTABLE_FIELDS:
        raise Problem(422, "Camp d'ordenació no admès", "validation")
    return field, descending


@router.get("/users", tags=["users"], operation_id="listUsers")
async def list_users(
    session: SessionDep,
    _authz: Annotated[authz.AuthzContext, Depends(authz.Authorize("users:read"))],
    page_size: Annotated[int, Query(alias="page[size]", ge=1, le=500)] = 50,
    page_cursor: Annotated[str | None, Query(alias="page[cursor]")] = None,
    active: Annotated[bool | None, Query(alias="filter[active]")] = None,
    role: Annotated[UserRole | None, Query(alias="filter[role]")] = None,
    department_id: Annotated[int | None, Query(alias="filter[department_id]")] = None,
    sort: str = "name",
) -> PagedUsersResponse:
    sort_field, descending = _parse_sort(sort)
    users, total, next_cursor = await repository.list_users(
        session,
        active=active,
        role=role,
        department_id=department_id,
        sort_field=sort_field,
        descending=descending,
        page_size=page_size,
        cursor=page_cursor,
    )
    return PagedUsersResponse(
        data=[UserResponse.from_user(u) for u in users],
        meta=PageMeta(total=total, next_cursor=next_cursor),
    )


@router.post("/users", tags=["users"], operation_id="createUser", status_code=201)
async def create_user(
    body: UserCreate,
    authz_ctx: Annotated[authz.AuthzContext, Depends(authz.Authorize("users:write"))],
    session: SessionDep,
    ctx: ContextDep,
) -> UserResponse:
    user = await management.create_user(session, body, authz_ctx.user, ctx)
    return UserResponse.from_user(user)


@router.get("/users/{id}", tags=["users"], operation_id="getUser")
async def get_user(
    id: Annotated[int, Path(ge=1)],
    session: SessionDep,
    _authz: Annotated[authz.AuthzContext, Depends(authz.Authorize("users:read"))],
) -> UserResponse:
    return UserResponse.from_user(await management.get_user(session, id))


@router.patch("/users/{id}", tags=["users"], operation_id="updateUser")
async def update_user(
    id: Annotated[int, Path(ge=1)],
    body: UserUpdate,
    authz_ctx: Annotated[authz.AuthzContext, Depends(authz.Authorize("users:write"))],
    session: SessionDep,
    ctx: ContextDep,
) -> UserResponse:
    user = await management.update_user(session, id, body, authz_ctx.user, ctx)
    return UserResponse.from_user(user)


@router.delete("/users/{id}", tags=["users"], operation_id="deactivateUser", status_code=204)
async def deactivate_user(
    id: Annotated[int, Path(ge=1)],
    authz_ctx: Annotated[authz.AuthzContext, Depends(authz.Authorize("users:write"))],
    session: SessionDep,
    ctx: ContextDep,
) -> None:
    await management.deactivate_user(session, id, authz_ctx.user, ctx)
