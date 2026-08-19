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


def _is_trusted_proxy(peer: str, trusted: list[str]) -> bool:
    """Accepta IPs exactes i rangs CIDR.

    Amb Docker el proxy no arriba mai amb la IP del servidor: si corre al
    host, el contenidor veu la passarel·la de la xarxa del compose, i si
    és un contenidor, una IP que canvia a cada reinici. Per això cal
    poder declarar el rang (p. ex. 172.16.0.0/12).
    """
    address = ipaddress.ip_address(peer)
    for entry in trusted:
        try:
            if address in ipaddress.ip_network(entry.strip(), strict=False):
                return True
        except ValueError:  # entrada mal escrita: s'ignora, mai es confia
            continue
    return False


def client_ip(request: Request) -> str | None:
    """IP real del client, amb X-Forwarded-For NOMÉS si la connexió ve d'un
    proxy declarat a `trusted_proxy_ips` (docs/06-seguretat.md §5).

    Sense aquesta comprovació la capçalera seria falsificable (qualsevol
    podria dir que ve d'una altra IP i saltar-se el límit de login); amb
    la llista buida, mai es mira la capçalera.
    """
    from app.core.config import settings

    peer = _valid_ip(request.client.host if request.client else None)
    if peer is None or not _is_trusted_proxy(peer, settings.trusted_proxy_ips):
        return peer
    forwarded = request.headers.get("x-forwarded-for", "")
    # El primer valor de la cadena és el client original; la resta són
    # proxys intermedis.
    for candidate in forwarded.split(","):
        resolved = _valid_ip(candidate.strip())
        if resolved is not None:
            return resolved
    return peer


def get_request_context(request: Request) -> RequestContext:
    return RequestContext(
        ip=client_ip(request),
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
