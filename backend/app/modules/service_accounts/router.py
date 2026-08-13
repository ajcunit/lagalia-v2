"""Gestió de service accounts / API keys (specs/service-accounts.md). Admin."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Path
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import authz
from app.core.db import get_session
from app.core.problems import Problem
from app.modules.audit.models import AuditActorType
from app.modules.audit.service import record_audit
from app.modules.service_accounts.models import ServiceAccount
from app.modules.service_accounts.service import generate_key, hash_key
from app.modules.users.dependencies import get_request_context
from app.modules.users.service import RequestContext

router = APIRouter(tags=["service-accounts"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
ContextDep = Annotated[RequestContext, Depends(get_request_context)]
ManageDep = Annotated[authz.AuthzContext, Depends(authz.Authorize("service_accounts:manage"))]
ResourceId = Annotated[int, Path(ge=1)]


class ServiceAccountCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    description: str | None = Field(default=None, max_length=1000)
    scopes: list[str] = Field(min_length=1, max_length=30)
    expires_at: datetime | None = None


class ServiceAccountUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    description: str | None = Field(default=None, max_length=1000)
    scopes: list[str] | None = Field(default=None, min_length=1, max_length=30)
    active: bool | None = None
    expires_at: datetime | None = None


class ServiceAccountResponse(BaseModel):
    id: int
    name: str
    description: str | None = None
    key_prefix: str
    scopes: list[str]
    active: bool
    expires_at: datetime | None = None
    last_used_at: datetime | None = None
    created_at: datetime

    @classmethod
    def from_account(cls, account: ServiceAccount) -> "ServiceAccountResponse":
        return cls(
            id=account.id,
            name=account.name,
            description=account.description,
            key_prefix=account.key_prefix,
            scopes=account.scopes,
            active=account.active,
            expires_at=account.expires_at,
            last_used_at=account.last_used_at,
            created_at=account.created_at,
        )


class ServiceAccountCreated(ServiceAccountResponse):
    key: str  # NOMÉS a la resposta de creació


def _validate_scopes(scopes: list[str]) -> None:
    unknown = sorted(set(scopes) - set(authz.PERMISSION_MATRIX))
    if unknown:
        raise Problem(
            422,
            "Scopes desconeguts",
            "validation",
            detail=f"No són accions de la matriu A2: {', '.join(unknown)}",
        )


async def _audit(
    session: AsyncSession, user_id: int, action: str, account_id: int, ctx: RequestContext
) -> None:
    await record_audit(
        session,
        actor_type=AuditActorType.USER,
        action=action,
        success=True,
        actor_id=user_id,
        resource_type="service_account",
        resource_id=str(account_id),
        ip=ctx.ip,
        user_agent=ctx.user_agent,
        trace_id=ctx.trace_id,
    )


@router.get("/service-accounts", operation_id="listServiceAccounts")
async def list_service_accounts(
    session: SessionDep, _authz: ManageDep
) -> dict[str, list[ServiceAccountResponse]]:
    accounts = (await session.execute(select(ServiceAccount).order_by(ServiceAccount.id))).scalars()
    return {"data": [ServiceAccountResponse.from_account(a) for a in accounts]}


@router.post("/service-accounts", operation_id="createServiceAccount", status_code=201)
async def create_service_account(
    body: ServiceAccountCreate, session: SessionDep, authz_ctx: ManageDep, ctx: ContextDep
) -> ServiceAccountCreated:
    _validate_scopes(body.scopes)
    key = generate_key()
    account = ServiceAccount(
        name=body.name,
        description=body.description,
        key_prefix=key[:12],
        key_hash=hash_key(key),
        scopes=body.scopes,
        expires_at=body.expires_at,
        created_by=authz_ctx.user.id,
    )
    session.add(account)
    await session.flush()
    await _audit(session, authz_ctx.user.id, "service_accounts.create", account.id, ctx)
    await session.commit()
    base = ServiceAccountResponse.from_account(account)
    return ServiceAccountCreated(**base.model_dump(), key=key)


@router.patch("/service-accounts/{id}", operation_id="updateServiceAccount")
async def update_service_account(
    id: ResourceId,
    body: ServiceAccountUpdate,
    session: SessionDep,
    authz_ctx: ManageDep,
    ctx: ContextDep,
) -> ServiceAccountResponse:
    account = await session.get(ServiceAccount, id)
    if account is None:
        raise Problem(404, "Service account no trobat", "not-found")
    changes = body.model_dump(exclude_unset=True)
    if "scopes" in changes:
        _validate_scopes(changes["scopes"])
    for field, value in changes.items():
        setattr(account, field, value)
    await session.flush()
    await _audit(session, authz_ctx.user.id, "service_accounts.update", account.id, ctx)
    await session.commit()
    return ServiceAccountResponse.from_account(account)


@router.delete("/service-accounts/{id}", operation_id="deleteServiceAccount", status_code=204)
async def delete_service_account(
    id: ResourceId, session: SessionDep, authz_ctx: ManageDep, ctx: ContextDep
) -> None:
    account = await session.get(ServiceAccount, id)
    if account is None:
        raise Problem(404, "Service account no trobat", "not-found")
    await session.delete(account)
    await session.flush()
    await _audit(session, authz_ctx.user.id, "service_accounts.delete", id, ctx)
    await session.commit()
