import ipaddress
import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.problems import unauthorized
from app.core.security import InvalidAccessTokenError, decode_access_token
from app.core.tracing import current_trace_id
from app.modules.users import repository
from app.modules.users.models import User
from app.modules.users.service import RequestContext

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class CurrentSession:
    user: User
    session_id: uuid.UUID


def _valid_ip(host: str | None) -> str | None:
    """La columna created_ip és INET: mai s'hi desa res que no sigui una IP."""
    if host is None:
        return None
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return None
    return host


def get_request_context(request: Request) -> RequestContext:
    return RequestContext(
        ip=_valid_ip(request.client.host if request.client else None),
        user_agent=request.headers.get("user-agent"),
        trace_id=current_trace_id(),
    )


async def get_current_session(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CurrentSession:
    if credentials is None:
        raise unauthorized()
    try:
        claims = decode_access_token(credentials.credentials)
    except InvalidAccessTokenError:
        raise unauthorized() from None

    user = await repository.get_user_by_id(session, claims.user_id)
    if user is None or not user.active:
        raise unauthorized()
    return CurrentSession(user=user, session_id=claims.session_id)
