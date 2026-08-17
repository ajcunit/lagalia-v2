"""Informe d'auditoria programat (specs/ai-refinements.md; 07 §2.2).

Mensual: red flags (SQL) → informe de l'agent auditor → correu als
destinataris configurats + esdeveniment. Mai tomba el scheduler.
"""

from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import text

from app.ai import audit_agent, providers
from app.core.db import session_factory
from app.integrations import hub
from app.integrations.smtp.connector import SmtpConnector
from app.jobs.registry import JobContext, job
from app.modules.webhooks.service import emit_event

logger = structlog.get_logger()

RECIPIENTS_SETTING = "reports.audit_recipients"


async def _recipients() -> list[str]:
    async with session_factory() as session:
        raw = (
            await session.execute(
                text("SELECT value FROM settings WHERE key = :k"), {"k": RECIPIENTS_SETTING}
            )
        ).scalar_one_or_none()
    if not raw:
        return []
    value = raw if isinstance(raw, str) else str(raw)
    return [part.strip() for part in value.replace(";", ",").split(",") if "@" in part]


async def _smtp() -> SmtpConnector | None:
    async with session_factory() as session:
        record = await hub.ensure_registered(session, "smtp")
        if not record.enabled:
            await session.commit()
            return None
        connector = await hub.get_connector(session, "smtp")
        await session.commit()
    return connector if isinstance(connector, SmtpConnector) else None


async def build_and_send() -> dict[str, Any]:
    """Genera l'informe i l'envia; retorna el resum del que ha passat."""
    result: dict[str, Any] = {"generated": False, "emailed": 0, "detail": None}
    try:
        async with session_factory() as session:
            report = await audit_agent.generate_report(
                session, custom_prompt="Informe mensual de seguiment per a Intervenció."
            )
        result["generated"] = True
    except providers.ProviderError as exc:
        result["detail"] = f"IA no disponible: {exc}"
        return result
    except Exception as exc:  # cap error tomba el scheduler
        result["detail"] = f"{type(exc).__name__}: {exc}"
        return result

    markdown = report["report_markdown"]
    recipients = await _recipients()
    smtp = await _smtp()
    if recipients and smtp is not None:
        month = datetime.now(UTC).strftime("%m/%Y")
        try:
            await smtp.send_mail(
                recipients,
                f"[LAGALia] Informe d'auditoria de contractació {month}",
                markdown,
            )
            result["emailed"] = len(recipients)
        except Exception as exc:  # noqa: BLE001 — el correu no ha de tombar el job
            result["detail"] = f"correu fallit: {exc}"
    elif not recipients:
        result["detail"] = f"sense destinataris (configura «{RECIPIENTS_SETTING}»)"
    else:
        result["detail"] = "connector smtp desactivat"

    async with session_factory() as session:
        await emit_event(
            session,
            "audit.report_ready",
            {
                "generated_at": report["generated_at"],
                "model": report["model"],
                "emailed": result["emailed"],
                "excerpt": markdown[:500],
            },
        )
        await session.commit()
    return result


@job("reports.audit_monthly")
async def audit_monthly(ctx: JobContext) -> dict[str, Any]:
    result = await build_and_send()
    logger.info("audit_monthly_finished", **result)
    return result
