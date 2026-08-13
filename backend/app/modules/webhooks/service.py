"""Emissió (outbox) i despatxament de webhooks (specs/outbound-webhooks.md)."""

import hashlib
import hmac
import json
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import structlog
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import DecryptionError, decrypt_value
from app.core.problems import Problem
from app.modules.webhooks.models import (
    DeliveryStatus,
    OutboundWebhook,
    OutboxEvent,
    WebhookDelivery,
)

logger = structlog.get_logger()

MAX_ATTEMPTS = 8
BASE_BACKOFF_SECONDS = 30
SEND_TIMEOUT_SECONDS = 10.0


async def emit_event(
    session: AsyncSession,
    *,
    event_type: str,
    aggregate: str,
    aggregate_id: str | int,
    data: dict[str, Any],
) -> None:
    """S'escriu a la MATEIXA transacció que el canvi de negoci (outbox)."""
    event_id = uuid.uuid4()
    session.add(
        OutboxEvent(
            event_id=event_id,
            event_type=event_type,
            aggregate=aggregate,
            aggregate_id=str(aggregate_id),
            payload={
                "id": str(event_id),
                "source": "lagalia",
                "type": event_type,
                "time": datetime.now(UTC).isoformat(),
                "subject": f"{aggregate}/{aggregate_id}",
                "data": data,
            },
        )
    )
    await session.flush()


async def enqueue_dispatch(_session: AsyncSession | None = None) -> None:
    """Encua el despatxador (un de sol en cua; el scheduler també el llança).

    SEMPRE amb sessió pròpia: el conflicte de dedup fa rollback, i si fos
    la sessió del caller li expiraria els objectes ja carregats.
    """
    from app.core.db import session_factory
    from app.jobs.service import enqueue_job

    async with session_factory() as own:
        try:
            await enqueue_job(own, job_type="webhooks.dispatch", dedup_key="webhooks.dispatch")
        except Problem:
            pass  # ja n'hi ha un de pendent


def sign(secret: str, timestamp: int, body: bytes) -> str:
    digest = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _client() -> httpx.AsyncClient:
    """Separat perquè els tests hi injectin un MockTransport.

    OUTBOUND_CA_BUNDLE permet confiar en CA internes (n8n municipal amb
    certificat propi) SENSE desactivar mai la verificació (06 §2).
    """
    from app.core.config import settings

    verify: bool | str = settings.outbound_ca_bundle or True
    return httpx.AsyncClient(timeout=SEND_TIMEOUT_SECONDS, verify=verify)


async def publish_outbox(session: AsyncSession) -> int:
    """Crea deliveries per als esdeveniments no publicats. Retorna publicats."""
    events = list(
        (
            await session.execute(
                select(OutboxEvent)
                .where(OutboxEvent.published_at.is_(None))
                .order_by(OutboxEvent.id.asc())
                .limit(200)
            )
        ).scalars()
    )
    if not events:
        return 0
    webhooks = list(
        (await session.execute(select(OutboundWebhook).where(OutboundWebhook.active))).scalars()
    )
    now = datetime.now(UTC)
    for event in events:
        for webhook in webhooks:
            if "*" in webhook.events or event.event_type in webhook.events:
                session.add(
                    WebhookDelivery(
                        webhook_id=webhook.id,
                        event_type=event.event_type,
                        payload=event.payload,
                    )
                )
        event.published_at = now
    await session.flush()
    return len(events)


async def send_due_deliveries(session: AsyncSession) -> dict[str, int]:
    """Envia les deliveries pendents vençudes, amb backoff exponencial."""
    now = datetime.now(UTC)
    deliveries = list(
        (
            await session.execute(
                select(WebhookDelivery)
                .where(
                    WebhookDelivery.status == DeliveryStatus.PENDING,
                    or_(
                        WebhookDelivery.next_retry_at.is_(None),
                        WebhookDelivery.next_retry_at <= now,
                    ),
                )
                .order_by(WebhookDelivery.id.asc())
                .limit(100)
            )
        ).scalars()
    )
    counters = {"delivered": 0, "retried": 0, "failed": 0}
    if not deliveries:
        return counters

    webhooks = {
        w.id: w
        for w in (
            await session.execute(
                select(OutboundWebhook).where(
                    OutboundWebhook.id.in_({d.webhook_id for d in deliveries})
                )
            )
        ).scalars()
    }

    async with _client() as client:
        for delivery in deliveries:
            webhook = webhooks.get(delivery.webhook_id)
            if webhook is None or not webhook.active:
                delivery.status = DeliveryStatus.FAILED
                delivery.last_error = "webhook inactiu o eliminat"
                counters["failed"] += 1
                continue

            body = json.dumps(delivery.payload, ensure_ascii=False).encode()
            timestamp = int(time.time())
            try:
                secret = decrypt_value(webhook.secret_encrypted)
            except DecryptionError:
                # Clau de xifrat incorrecta (entorn/rotació): s'ajorna sense
                # cremar intents — es recupera sol quan la clau sigui bona.
                delivery.last_error = "secret indesxifrable (clau de xifrat de l'entorn?)"
                delivery.next_retry_at = now + timedelta(seconds=BASE_BACKOFF_SECONDS * 4)
                counters["retried"] += 1
                continue
            headers = {
                "Content-Type": "application/json",
                "X-Webhook-Id": str(webhook.id),
                "X-Timestamp": str(timestamp),
                "X-Signature": sign(secret, timestamp, body),
            }
            delivery.attempts += 1
            try:
                response = await client.post(webhook.url, content=body, headers=headers)
                if 200 <= response.status_code < 300:
                    delivery.status = DeliveryStatus.DELIVERED
                    delivery.last_error = None
                    delivery.next_retry_at = None
                    counters["delivered"] += 1
                    continue
                delivery.last_error = f"HTTP {response.status_code}"
            except httpx.HTTPError as exc:
                delivery.last_error = f"{type(exc).__name__}: {exc}"

            if delivery.attempts >= MAX_ATTEMPTS:
                delivery.status = DeliveryStatus.FAILED
                delivery.next_retry_at = None
                counters["failed"] += 1
                logger.warning(
                    "webhook_delivery_failed",
                    delivery_id=delivery.id,
                    webhook_id=webhook.id,
                    error=delivery.last_error,
                )
            else:
                delivery.next_retry_at = now + timedelta(
                    seconds=BASE_BACKOFF_SECONDS * (2**delivery.attempts)
                )
                counters["retried"] += 1
    await session.flush()
    return counters
