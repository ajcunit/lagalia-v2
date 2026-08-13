"""Endpoints de webhooks sortints (specs/outbound-webhooks.md). Admin."""

import secrets
from datetime import datetime
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Path
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import authz
from app.core.config import settings
from app.core.crypto import encrypt_value
from app.core.db import get_session
from app.core.problems import Problem
from app.modules.audit.models import AuditActorType
from app.modules.audit.service import record_audit
from app.modules.users.dependencies import get_request_context
from app.modules.users.service import RequestContext
from app.modules.webhooks.models import OutboundWebhook, WebhookDelivery
from app.modules.webhooks.service import emit_event, enqueue_dispatch

router = APIRouter(tags=["webhooks"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
ContextDep = Annotated[RequestContext, Depends(get_request_context)]
ManageDep = Annotated[authz.AuthzContext, Depends(authz.Authorize("webhooks:manage"))]
ResourceId = Annotated[int, Path(ge=1)]


class WebhookCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    url: str = Field(min_length=8, max_length=1000)
    events: list[str] = Field(min_length=1, max_length=50)


class WebhookUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    url: str | None = Field(default=None, min_length=8, max_length=1000)
    events: list[str] | None = Field(default=None, min_length=1, max_length=50)
    active: bool | None = None


class WebhookResponse(BaseModel):
    id: int
    name: str
    url: str
    events: list[str]
    active: bool
    secret_is_set: bool = True
    created_at: datetime

    @classmethod
    def from_webhook(cls, webhook: OutboundWebhook) -> "WebhookResponse":
        return cls(
            id=webhook.id,
            name=webhook.name,
            url=webhook.url,
            events=webhook.events,
            active=webhook.active,
            created_at=webhook.created_at,
        )


class WebhookCreated(WebhookResponse):
    secret: str  # NOMÉS a la resposta de creació


class DeliveryResponse(BaseModel):
    id: int
    event_type: str
    status: str
    attempts: int
    last_error: str | None = None
    next_retry_at: datetime | None = None
    created_at: datetime

    @classmethod
    def from_delivery(cls, delivery: WebhookDelivery) -> "DeliveryResponse":
        return cls(
            id=delivery.id,
            event_type=delivery.event_type,
            status=delivery.status.value,
            attempts=delivery.attempts,
            last_error=delivery.last_error,
            next_retry_at=delivery.next_retry_at,
            created_at=delivery.created_at,
        )


def _validate_url(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme == "https":
        return
    if parts.scheme == "http" and settings.environment == "development":
        return  # n8n local en desenvolupament
    raise Problem(422, "La URL del webhook ha de ser https", "validation")


async def _audit(
    session: AsyncSession, user_id: int, action: str, webhook_id: int, ctx: RequestContext
) -> None:
    await record_audit(
        session,
        actor_type=AuditActorType.USER,
        action=action,
        success=True,
        actor_id=user_id,
        resource_type="webhook",
        resource_id=str(webhook_id),
        ip=ctx.ip,
        user_agent=ctx.user_agent,
        trace_id=ctx.trace_id,
    )


@router.get("/webhooks", operation_id="listWebhooks")
async def list_webhooks(session: SessionDep, _authz: ManageDep) -> dict[str, list[WebhookResponse]]:
    webhooks = (
        await session.execute(select(OutboundWebhook).order_by(OutboundWebhook.id))
    ).scalars()
    return {"data": [WebhookResponse.from_webhook(w) for w in webhooks]}


@router.post("/webhooks", operation_id="createWebhook", status_code=201)
async def create_webhook(
    body: WebhookCreate, session: SessionDep, authz_ctx: ManageDep, ctx: ContextDep
) -> WebhookCreated:
    _validate_url(body.url)
    secret = f"whsec_{secrets.token_urlsafe(32)}"
    webhook = OutboundWebhook(
        name=body.name,
        url=body.url,
        events=body.events,
        secret_encrypted=encrypt_value(secret),
    )
    session.add(webhook)
    await session.flush()
    await _audit(session, authz_ctx.user.id, "webhooks.create", webhook.id, ctx)
    await session.commit()
    base = WebhookResponse.from_webhook(webhook)
    return WebhookCreated(**base.model_dump(), secret=secret)


@router.patch("/webhooks/{id}", operation_id="updateWebhook")
async def update_webhook(
    id: ResourceId,
    body: WebhookUpdate,
    session: SessionDep,
    authz_ctx: ManageDep,
    ctx: ContextDep,
) -> WebhookResponse:
    webhook = await session.get(OutboundWebhook, id)
    if webhook is None:
        raise Problem(404, "Webhook no trobat", "not-found")
    changes = body.model_dump(exclude_unset=True)
    if "url" in changes:
        _validate_url(changes["url"])
    for field, value in changes.items():
        setattr(webhook, field, value)
    await session.flush()
    await _audit(session, authz_ctx.user.id, "webhooks.update", webhook.id, ctx)
    await session.commit()
    return WebhookResponse.from_webhook(webhook)


@router.delete("/webhooks/{id}", operation_id="deleteWebhook", status_code=204)
async def delete_webhook(
    id: ResourceId, session: SessionDep, authz_ctx: ManageDep, ctx: ContextDep
) -> None:
    webhook = await session.get(OutboundWebhook, id)
    if webhook is None:
        raise Problem(404, "Webhook no trobat", "not-found")
    await session.delete(webhook)
    await session.flush()
    await _audit(session, authz_ctx.user.id, "webhooks.delete", id, ctx)
    await session.commit()


@router.get("/webhooks/{id}/deliveries", operation_id="listWebhookDeliveries")
async def list_webhook_deliveries(
    id: ResourceId, session: SessionDep, _authz: ManageDep
) -> dict[str, list[DeliveryResponse]]:
    if await session.get(OutboundWebhook, id) is None:
        raise Problem(404, "Webhook no trobat", "not-found")
    deliveries = (
        await session.execute(
            select(WebhookDelivery)
            .where(WebhookDelivery.webhook_id == id)
            .order_by(WebhookDelivery.id.desc())
            .limit(100)
        )
    ).scalars()
    return {"data": [DeliveryResponse.from_delivery(d) for d in deliveries]}


@router.post("/webhooks/{id}/actions/test", operation_id="testWebhook", status_code=202)
async def test_webhook(
    id: ResourceId, session: SessionDep, authz_ctx: ManageDep, ctx: ContextDep
) -> dict[str, str]:
    webhook = await session.get(OutboundWebhook, id)
    if webhook is None:
        raise Problem(404, "Webhook no trobat", "not-found")
    # Delivery directa només per a aquest webhook (sense passar per l'outbox).
    now = (await session.execute(select(func.now()))).scalar_one()
    session.add(
        WebhookDelivery(
            webhook_id=webhook.id,
            event_type="webhook.test",
            payload={
                "id": f"test-{webhook.id}-{int(now.timestamp())}",
                "source": "lagalia",
                "type": "webhook.test",
                "time": now.isoformat(),
                "subject": f"webhook/{webhook.id}",
                "data": {"message": "Prova de connexió des de LAGALia"},
            },
        )
    )
    await session.flush()
    await _audit(session, authz_ctx.user.id, "webhooks.test", webhook.id, ctx)
    await session.commit()
    await enqueue_dispatch(session)
    return {"status": "queued"}


__all__ = ["router", "emit_event"]
