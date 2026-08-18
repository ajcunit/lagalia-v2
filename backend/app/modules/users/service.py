"""Casos d'ús d'autenticació: login, rotació de refresh, logout.

Tots els camins (èxit i error) escriuen auditoria ABANS de respondre;
els errors es materialitzen com a Problem després de fer commit de
l'entrada d'auditoria.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.problems import Problem, unauthorized
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_refresh_token,
    verify_password,
)
from app.modules.audit.models import AuditActorType
from app.modules.audit.service import record_audit
from app.modules.users import repository
from app.modules.users.models import User
from app.modules.users.schemas import TokenPairResponse


@dataclass(frozen=True)
class RequestContext:
    ip: str | None
    user_agent: str | None
    trace_id: str | None


async def _audit_auth(
    session: AsyncSession,
    action: str,
    success: bool,
    ctx: RequestContext,
    *,
    actor_id: int | None = None,
    email: str | None = None,
) -> None:
    await record_audit(
        session,
        actor_type=AuditActorType.USER,
        action=action,
        success=success,
        actor_id=actor_id,
        resource_type="session",
        ip=ctx.ip,
        user_agent=ctx.user_agent,
        trace_id=ctx.trace_id,
        details={"email": email} if email else None,
    )


async def _issue_token_pair(
    session: AsyncSession, user: User, family_id: uuid.UUID, ctx: RequestContext
) -> TokenPairResponse:
    refresh_token = generate_refresh_token()
    await repository.create_refresh_token(
        session,
        token_hash=hash_refresh_token(refresh_token),
        user_id=user.id,
        family_id=family_id,
        expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days),
        created_ip=ctx.ip,
    )
    access_token, expires_in = create_access_token(user.id, family_id)
    return TokenPairResponse(
        access_token=access_token, refresh_token=refresh_token, expires_in=expires_in
    )


async def login(
    session: AsyncSession, email: str, password: str, ctx: RequestContext
) -> TokenPairResponse:
    user = await repository.get_user_by_email(session, email)
    password_ok = verify_password(password, user.password_hash if user else None)

    # Usuari de directori (sense contrasenya local) o desconegut: intent LDAP
    # si el connector està habilitat. L'AD caigut no trenca el flux local.
    if not password_ok and (user is None or user.password_hash is None):
        from app.modules.users import ldap_auth

        ldap_result = await ldap_auth.try_ldap_login(session, email, password)
        if ldap_result is not None:
            user, password_ok = ldap_result.user, True
            if ldap_result.provisioned:
                await _audit_auth(
                    session, "auth.ldap_provision", True, ctx, actor_id=user.id, email=user.email
                )

    if user is None or not password_ok:
        await _audit_auth(session, "auth.login", False, ctx, email=email)
        await session.commit()
        raise unauthorized("Credencials incorrectes")

    if not user.active:
        await _audit_auth(session, "auth.login", False, ctx, actor_id=user.id, email=email)
        await session.commit()
        raise Problem(403, "Compte desactivat", "account-disabled")

    pair = await _issue_token_pair(session, user, uuid.uuid4(), ctx)
    await _audit_auth(session, "auth.login", True, ctx, actor_id=user.id, email=email)
    await session.commit()
    return pair


async def refresh(
    session: AsyncSession, refresh_token: str, ctx: RequestContext
) -> TokenPairResponse:
    stored = await repository.get_refresh_token_by_hash(session, hash_refresh_token(refresh_token))

    if stored is None:
        await _audit_auth(session, "auth.refresh", False, ctx)
        await session.commit()
        raise unauthorized()

    if stored.revoked_at is not None:
        # Token ja rotat o revocat: reutilització → cau la família sencera.
        await repository.revoke_token_family(session, stored.family_id)
        await _audit_auth(session, "auth.refresh_reuse", False, ctx, actor_id=stored.user_id)
        await session.commit()
        raise unauthorized()

    user = await repository.get_user_by_id(session, stored.user_id)
    expired = stored.expires_at <= datetime.now(UTC)
    if expired or user is None or not user.active:
        await _audit_auth(session, "auth.refresh", False, ctx, actor_id=stored.user_id)
        await session.commit()
        raise unauthorized()

    await repository.revoke_refresh_token(session, stored)
    pair = await _issue_token_pair(session, user, stored.family_id, ctx)
    await _audit_auth(session, "auth.refresh", True, ctx, actor_id=user.id)
    await session.commit()
    return pair


async def logout(
    session: AsyncSession, user: User, session_id: uuid.UUID, ctx: RequestContext
) -> None:
    await repository.revoke_token_family(session, session_id)
    await _audit_auth(session, "auth.logout", True, ctx, actor_id=user.id)
    await session.commit()
