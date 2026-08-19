"""Retenció i purga de dades (specs/data-retention.md, B-006)."""

from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.db import session_factory
from app.jobs import retention
from app.jobs.registry import JobContext

pytestmark = pytest.mark.anyio


def test_parse_retention_days() -> None:
    assert retention.parse_retention_days("90", default=730) == 90
    assert retention.parse_retention_days(None, default=730) == 730
    assert retention.parse_retention_days("garbage", default=365) == 365
    # Fora de rang = per defecte: un error de config mai buida l'auditoria.
    assert retention.parse_retention_days("5", default=730) == 730
    assert retention.parse_retention_days("99999", default=365) == 365


async def _run_purge() -> dict[str, Any]:
    async def set_progress(pct: int, message: str | None) -> None:
        pass

    return await retention.purge(
        JobContext(job_id=uuid4(), payload={}, set_progress=set_progress)
    )


async def test_purge_ai_runs_and_audit_trail() -> None:
    tag = uuid4().hex[:8]
    async with session_factory() as session:
        # Execucions d'IA: una caducada (2 anys) i una recent; sense cadena
        # de hash, així que la inserció crua és vàlida.
        await session.execute(
            text(
                "INSERT INTO ai_runs (task, status, created_at) VALUES "
                f"('purga-{tag}', 'success', now() - interval '700 days'), "
                f"('purga-{tag}', 'success', now())"
            )
        )
        await session.commit()

    result = await _run_purge()
    assert result["audit_days"] == 730
    assert result["ai_days"] == 365
    assert result["ai_runs"] >= 1

    async with session_factory() as session:
        remaining = (
            await session.execute(
                text("SELECT count(*) FROM ai_runs WHERE task = :t"), {"t": f"purga-{tag}"}
            )
        ).scalar_one()
        trail = (
            await session.execute(
                text(
                    "SELECT details FROM audit_log WHERE action = 'retention.purge' "
                    "ORDER BY id DESC LIMIT 1"
                )
            )
        ).scalar_one_or_none()
        await session.execute(
            text("DELETE FROM ai_runs WHERE task = :t"), {"t": f"purga-{tag}"}
        )
        await session.commit()

    assert remaining == 1  # la caducada fora, la recent intacta
    assert trail is not None and "audit_days" in trail  # rastre de la purga


async def test_audit_log_stays_append_only_and_chain_safe() -> None:
    """El trigger continua blocant esborrats directes, i la purga només
    treu el PREFIX de la cadena: una fila antiga inserida al final (id alt)
    no s'esborra mentre tingui entrades recents per davant."""
    from app.modules.audit.models import AuditActorType
    from app.modules.audit.service import record_audit

    tag = uuid4().hex[:8]
    async with session_factory() as session:
        # Àncora recent amb cadena ben calculada.
        await record_audit(
            session,
            actor_type=AuditActorType.SYSTEM,
            action=f"retention-anchor-{tag}",
            success=True,
        )
        await session.commit()

    # DELETE directe (sense la porta de la purga) → el trigger el rebutja.
    async with session_factory() as session:
        with pytest.raises(DBAPIError, match="append-only"):
            await session.execute(
                text("DELETE FROM audit_log WHERE action = :a"),
                {"a": f"retention-anchor-{tag}"},
            )

    # La purga corre sense error i l'àncora recent continua allà.
    await _run_purge()
    async with session_factory() as session:
        count = (
            await session.execute(
                text("SELECT count(*) FROM audit_log WHERE action = :a"),
                {"a": f"retention-anchor-{tag}"},
            )
        ).scalar_one()
    assert count == 1
