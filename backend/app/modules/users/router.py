"""Endpoints d'autenticació i perfil. Prims: la lògica és al servei."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import get_session
from app.core.ratelimit import enforce_rate_limit, parse_rate
from app.modules.users import service
from app.modules.users.dependencies import (
    CurrentSession,
    get_current_session,
    get_request_context,
)
from app.modules.users.schemas import (
    LoginRequest,
    RefreshRequest,
    TokenPairResponse,
    UserResponse,
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
